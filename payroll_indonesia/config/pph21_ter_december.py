"""
PPh21 December Progressive (Annual Correction) calculation module.

This module handles the December/annual income tax correction calculation
for Indonesian payroll using the progressive tax rates. It ONLY handles
December calculations, not regular monthly TER calculations.

IMPORTANT: This module only handles December/annual calculations.
           Regular monthly calculations must use pph21_ter.py
"""

from typing import Dict, Any, List, Union, Tuple, Optional
import frappe
from frappe import ValidationError
from frappe.utils import flt, getdate
from decimal import Decimal, ROUND_HALF_UP

from payroll_indonesia.config import get_ptkp_amount, config

DEFAULT_TAX_SLABS = [
    (60_000_000, 5),
    (250_000_000, 15),
    (500_000_000, 25),
    (5_000_000_000, 30),
    (float("inf"), 35),
]

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def get_tax_slabs() -> List[Tuple[float, float]]:
    slab_name = config.get_value("fallback_income_tax_slab")
    if not slab_name:
        return DEFAULT_TAX_SLABS
    try:
        slab_doc = frappe.get_cached_doc("Income Tax Slab", slab_name)
    except Exception:
        frappe.logger().warning(f"Income Tax Slab {slab_name} tidak ditemukan")
        return DEFAULT_TAX_SLABS

    slabs: List[Tuple[float, float]] = []
    for row in slab_doc.get("slabs", []) or []:
        batas = flt(row.get("to_amount", 0)) or 0.0
        if batas == 0:
            batas = float("inf")
        rate = flt(row.get("percent_deduction", 0)) or 0.0
        slabs.append((batas, rate))
    if not slabs:
        return DEFAULT_TAX_SLABS
    slabs.sort(key=lambda x: x[0])
    return slabs


def sum_bruto_earnings(salary_slip: Dict[str, Any]) -> float:
    total = 0.0
    for row in salary_slip.get("earnings", []) or []:
        if (
            (row.get("is_tax_applicable", 0) == 1
             or row.get("is_income_tax_component", 0) == 1
             or row.get("variable_based_on_taxable_salary", 0) == 1)
            and row.get("statistical_component", 0) == 0
            and row.get("exempted_from_income_tax", 0) == 0
        ):
            total += flt(row.get("amount", 0))
    return total


def sum_pengurang_netto_bulanan(salary_slip: Dict[str, Any]) -> float:
    total = 0.0
    for row in salary_slip.get("deductions", []) or []:
        if (
            (row.get("is_income_tax_component", 0) == 1
             or row.get("variable_based_on_taxable_salary", 0) == 1
             or row.get("is_pengurang_netto", 0) == 1)
            and row.get("do_not_include_in_total", 0) == 0
            and row.get("statistical_component", 0) == 0
            and "biaya jabatan" not in (row.get("salary_component", "") or "").lower()
        ):
            total += flt(row.get("amount", 0))
    return total


def biaya_jabatan_bulanan(bruto_bulan: float) -> float:
    return min(flt(bruto_bulan) * 0.05, 500_000.0)


def _get_monthly_jp_jht_employee(slip_dict: Optional[Dict[str, Any]]) -> float:
    if not slip_dict:
        return 0.0
    tot = 0.0
    for row in slip_dict.get("deductions", []) or []:
        nm = (row.get("salary_component") or "").strip().lower()
        if nm in {"bpjs jht employee", "bpjs jp employee"}:
            tot += flt(row.get("amount", 0))
    return tot


def _pph21_paid_in_slip(slip_dict: Dict[str, Any]) -> float:
    paid = flt(slip_dict.get("tax", 0))
    if paid:
        return paid
    names = {"pph 21", "pph21", "pph-21"}
    return sum(
        flt(d.get("amount", 0))
        for d in (slip_dict.get("deductions") or [])
        if (d.get("salary_component") or "").strip().lower() in names
    )


# --- pembulatan yang benar untuk PKP & PPh ---
def floor_to_thousand(x: float) -> int:
    return int(flt(x) // 1000) * 1000

def round_rupiah(x: float) -> int:
    return int(Decimal(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def calculate_pkp_annual(netto_total: float, ptkp_annual: float) -> float:
    pkp = max(flt(netto_total) - flt(ptkp_annual), 0.0)
    return floor_to_thousand(pkp)


def calculate_pph21_progressive(pkp_annual: float) -> float:
    pajak = 0.0
    pkp_left = flt(pkp_annual)
    lower = 0.0
    for batas, rate in get_tax_slabs():
        if pkp_left <= 0:
            break
        lap = min(pkp_left, batas - lower)
        pajak += lap * rate / 100.0
        pkp_left -= lap
        lower = batas
    return pajak

# ---------------------------------------------------------------------------
# MAIN (DECEMBER-ONLY FLOW)
# ---------------------------------------------------------------------------

def calculate_pph21_december(
    *,
    employee: Union[Dict[str, Any], Any],
    company: str,
    # APH (Jan–Nov) — hanya untuk total PPh Jan–Nov:
    ytd_bruto_jan_nov: float,
    ytd_netto_jan_nov: float,
    ytd_tax_paid_jan_nov: float,
    # Input Desember:
    bruto_desember: float,
    pengurang_netto_desember: float,
    biaya_jabatan_desember: float,
    # Opsional (salah satu boleh diisi):
    december_slip: Optional[Dict[str, Any]] = None,
    jp_jht_employee_month: Optional[float] = None,
) -> Dict[str, Any]:

    if not employee:
        frappe.throw("Employee data is required for PPh21 calculation", title="Missing Employee")
    if not company:
        frappe.throw("Company is required for PPh21 calculation", title="Missing Company")

    emp_type = employee.get("employment_type") if isinstance(employee, dict) else getattr(employee, "employment_type", None)
    if emp_type != "Full-time":
        return {
            "bruto_total": 0.0, "netto_total": 0.0, "ptkp_annual": 0.0, "pkp_annual": 0.0,
            "rate": "", "pph21_annual": 0.0, "pph21_bulan": 0.0, "koreksi_pph21": 0.0,
            "employment_type_checked": False,
            "message": "PPh21 December hanya dihitung untuk Employment Type: Full-time",
        }

    # --- December-only annualization ---
    bruto_des = flt(bruto_desember)
    # pastikan biaya jabatan bulanan sesuai formula (kalau caller kirim lebih dari 500k, kita clamp)
    bj_month = min(flt(biaya_jabatan_desember), 500_000.0, bruto_des * 0.05)
    bj_annual = min(bj_month * 12.0, 6_000_000.0)

    # JP+JHT (EE) bulan Desember (ambil dari argumen atau dari slip)
    if jp_jht_employee_month is None:
        jp_jht_employee_month = _get_monthly_jp_jht_employee(december_slip)
    jp_jht_employee_month = flt(jp_jht_employee_month)
    jp_jht_employee_annual = jp_jht_employee_month * 12.0

    # Bruto tahunan dari Desember
    bruto_annual = bruto_des * 12.0

    # Netto tahunan = Bruto tahunan - BJ tahunan - (JP+JHT EE × 12)
    # CATATAN: pengurang_netto_desember TIDAK di-annualize (sesuai arahan),
    # ia hanya informasi breakdown bulanan.
    netto_annual = bruto_annual - bj_annual - jp_jht_employee_annual

    # PTKP, PKP, PPh
    try:
        ptkp_annual = get_ptkp_amount(employee)
    except ValidationError:
        ptkp_annual = 0.0

    pkp_annual = calculate_pkp_annual(netto_annual, ptkp_annual)
    pph21_annual = round_rupiah(calculate_pph21_progressive(pkp_annual))

    koreksi_pph21 = pph21_annual - flt(ytd_tax_paid_jan_nov)
    pph21_bulan_des = koreksi_pph21

    rates = "/".join([f"{rate}%" for _, rate in get_tax_slabs()])

    # nilai netto_desember hanya untuk display (bukan dasar tahunan)
    netto_desember = bruto_des - bj_month - flt(pengurang_netto_desember)

    return {
        # breakdown Jan–Nov (display/audit)
        "bruto_jan_nov": flt(ytd_bruto_jan_nov),
        "netto_jan_nov": flt(ytd_netto_jan_nov),
        "pph21_paid_jan_nov": flt(ytd_tax_paid_jan_nov),

        # Desember (display)
        "bruto_desember": bruto_des,
        "pengurang_netto_desember": flt(pengurang_netto_desember),
        "biaya_jabatan_desember": bj_month,
        "netto_desember": netto_desember,
        "jp_jht_employee_month": jp_jht_employee_month,
        "jp_jht_employee_annual": jp_jht_employee_annual,

        # tahunan (DECEMBER-ONLY)
        "bruto_total": bruto_annual,
        "netto_total": netto_annual,

        # pajak
        "ptkp_annual": flt(ptkp_annual),
        "pkp_annual": flt(pkp_annual),
        "rate": rates,
        "pph21_annual": flt(pph21_annual),
        "pph21_bulan": flt(pph21_bulan_des),   # yang masuk ke slip Desember
        "koreksi_pph21": flt(koreksi_pph21),

        "employment_type_checked": True,
    }


def calculate_pph21_december_from_slips(
    employee: Union[Dict[str, Any], Any],
    company: str,
    salary_slips: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Versi uji cepat (tanpa APH):
    - Bruto, BJ, JP+JHT (EE) untuk annualization diambil dari slip Desember.
    - Total PPh Jan–Nov diambil dari slip Jan–Nov (untuk koreksi).
    """
    if not employee:
        frappe.throw("Employee data is required for PPh21 calculation", title="Missing Employee")
    if not company:
        frappe.throw("Company is required for PPh21 calculation", title="Missing Company")
    if not salary_slips:
        return {"message": "Daftar salary slip kosong.", "employment_type_checked": True}

    emp_type = employee.get("employment_type") if isinstance(employee, dict) \
        else getattr(employee, "employment_type", None)
    if emp_type != "Full-time":
        return {
            "bruto_jan_nov": 0.0, "bruto_desember": 0.0, "bruto_total": 0.0,
            "netto_total": 0.0, "ptkp_annual": 0.0, "pkp_annual": 0.0, "rate": "",
            "pph21_annual": 0.0, "pph21_bulan": 0.0, "income_tax_deduction_total": 0.0,
            "biaya_jabatan_total": 0.0, "koreksi_pph21": 0.0, "pph21_paid_jan_nov": 0.0,
            "employment_type_checked": False,
            "message": "PPh21 December hanya dihitung untuk Employment Type: Full-time",
        }

    jan_nov_slips: List[Dict[str, Any]] = []
    desember_slips: List[Dict[str, Any]] = []
    for s in salary_slips:
        d = s.get("start_date") or s.get("posting_date")
        mon = (d.month if hasattr(d, "month") else getdate(d).month) if d else None
        if mon == 12:
            desember_slips.append(s)
        else:
            jan_nov_slips.append(s)

    # total PPh Jan–Nov (untuk koreksi)
    pph21_paid_jan_nov = 0.0
    for s in jan_nov_slips:
        pph21_paid_jan_nov += _pph21_paid_in_slip(s)

    # annualization dari Desember saja (agregasi bila lebih dari 1 slip)
    bruto_desember = 0.0
    jp_jht_month = 0.0
    for s in desember_slips:
        bruto_desember += sum_bruto_earnings(s)
        jp_jht_month += _get_monthly_jp_jht_employee(s)

    bj_month = biaya_jabatan_bulanan(bruto_desember)
    bj_annual = min(bj_month * 12.0, 6_000_000.0)
    bruto_annual = bruto_desember * 12.0
    jp_jht_annual = jp_jht_month * 12.0
    netto_annual = bruto_annual - bj_annual - jp_jht_annual

    try:
        ptkp_annual = get_ptkp_amount(employee)
    except ValidationError:
        ptkp_annual = 0.0
    pkp_annual = calculate_pkp_annual(netto_annual, ptkp_annual)
    pph21_annual = round_rupiah(calculate_pph21_progressive(pkp_annual))

    koreksi_pph21 = pph21_annual - pph21_paid_jan_nov
    rates = "/".join([f"{rate}%" for _, rate in get_tax_slabs()])

    # netto_desember (display only)
    netto_desember_display = bruto_desember - bj_month

    return {
        "bruto_jan_nov": sum(sum_bruto_earnings(s) for s in jan_nov_slips),
        "netto_jan_nov": 0.0,  # tidak relevan untuk annualization Desember
        "pph21_paid_jan_nov": pph21_paid_jan_nov,

        "bruto_desember": bruto_desember,
        "pengurang_netto_desember": 0.0,
        "biaya_jabatan_desember": bj_month,
        "netto_desember": netto_desember_display,
        "jp_jht_employee_month": jp_jht_month,
        "jp_jht_employee_annual": jp_jht_annual,

        "bruto_total": bruto_annual,
        "netto_total": netto_annual,
        "ptkp_annual": ptkp_annual,
        "pkp_annual": pkp_annual,
        "rate": rates,
        "pph21_annual": pph21_annual,
        "pph21_bulan": koreksi_pph21,
        "koreksi_pph21": koreksi_pph21,
        "employment_type_checked": True,
    }
