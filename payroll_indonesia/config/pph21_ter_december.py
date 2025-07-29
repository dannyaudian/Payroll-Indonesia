import frappe
from frappe.utils import flt
from payroll_indonesia.config import (
    config,
    get_ptkp_amount,
    get_ter_code,
    get_ter_rate,
)

# Default progressive income tax slabs (PMK 168/2023, berlaku 2024)
DEFAULT_TAX_SLABS = [
    (60_000_000, 5),
    (250_000_000, 15),
    (500_000_000, 25),
    (5_000_000_000, 30),
    (float("inf"), 35),
]

def get_tax_slabs():
    """Ambil daftar tax slab dari dokumen Income Tax Slab di settings."""
    slab_name = config.get_value("fallback_income_tax_slab")
    if not slab_name:
        return DEFAULT_TAX_SLABS

    try:
        slab_doc = frappe.get_cached_doc("Income Tax Slab", slab_name)
    except Exception:
        frappe.logger().warning("Income Tax Slab %s tidak ditemukan", slab_name)
        return DEFAULT_TAX_SLABS

    slabs = []
    for row in slab_doc.get("slabs", []):
        batas = flt(row.to_amount or 0)
        if batas == 0:
            batas = float("inf")
        rate = flt(row.percent_deduction or 0)
        slabs.append((batas, rate))

    if not slabs:
        return DEFAULT_TAX_SLABS

    slabs.sort(key=lambda x: x[0])
    return slabs


def sum_bruto_earnings(salary_slip):
    """
    Jumlahkan seluruh komponen earning yang menambah penghasilan bruto (termasuk natura taxable).
    - is_tax_applicable = 1 (atau is_income_tax_component/variable_based_on_taxable_salary = 1)
    - do_not_include_in_total = 0
    - statistical_component = 0
    - exempted_from_income_tax = 0 (jika field ada)
    """
    total = 0.0
    for row in salary_slip.get("earnings", []):
        if (
            (row.get("is_tax_applicable", 0) == 1 or
             row.get("is_income_tax_component", 0) == 1 or
             row.get("variable_based_on_taxable_salary", 0) == 1)
            and row.get("do_not_include_in_total", 0) == 0
            and row.get("statistical_component", 0) == 0
            and row.get("exempted_from_income_tax", 0) == 0
        ):
            total += flt(row.amount)
    return total

def sum_income_tax_deductions(salary_slip):
    """
    Jumlahkan deduction pengurang netto (BPJS Kesehatan Employee, BPJS JHT Employee, BPJS JP Employee, dsb).
    - is_income_tax_component = 1 atau variable_based_on_taxable_salary = 1
    - do_not_include_in_total = 0
    - statistical_component = 0
    - EXCLUDE biaya jabatan!
    """
    total = 0.0
    for row in salary_slip.get("deductions", []):
        if (
            (row.get("is_income_tax_component", 0) == 1 or
             row.get("variable_based_on_taxable_salary", 0) == 1)
            and row.get("do_not_include_in_total", 0) == 0
            and row.get("statistical_component", 0) == 0
            and "biaya jabatan" not in row.get("salary_component", "").lower()
        ):
            total += flt(row.amount)
    return total

def get_biaya_jabatan_from_component(salary_slip):
    """
    Ambil nilai biaya jabatan dari komponen deduction 'Biaya Jabatan' jika tersedia pada salary slip.
    Jika tidak ditemukan, return 0.
    """
    for row in salary_slip.get("deductions", []):
        if "biaya jabatan" in row.get("salary_component", "").lower():
            return flt(row.amount)
    return 0.0

def sum_total_actual_netto_this_year(employee, salary_slips):
    """
    Menjumlah seluruh netto aktual dari slip gaji Januari sampai Desember.
    Netto bulanan = bruto - pengurang_netto - biaya_jabatan, sesuai slip salary masing-masing bulan.
    salary_slips: list of dict, setiap dict = salary_slip bulan berjalan
    """
    total_netto = 0.0
    for slip in salary_slips:
        bruto = sum_bruto_earnings(slip)
        pengurang_netto = sum_income_tax_deductions(slip)
        biaya_jabatan = get_biaya_jabatan_from_component(slip)
        total_netto += bruto - pengurang_netto - biaya_jabatan
    return total_netto

def calculate_pkp_annual(total_netto_actual, ptkp_annual):
    """
    PKP tahunan = (total netto setahun - PTKP setahun), dibulatkan ke ribuan terdekat.
    """
    pkp = max(total_netto_actual - ptkp_annual, 0)
    return int(round(pkp / 1000.0)) * 1000

def calculate_pph21_progressive(pkp_annual):
    """
    Hitung PPh 21 setahun dengan metode progresif (slab).
    Return: total pph setahun
    """
    pajak = 0
    pkp_left = pkp_annual
    lower_limit = 0

    for batas, rate in get_tax_slabs():
        if pkp_left <= 0:
            break
        lapisan = min(pkp_left, batas - lower_limit)
        pajak += lapisan * rate / 100
        pkp_left -= lapisan
        lower_limit = batas
    return pajak

def calculate_pph21_TER_december(employee, salary_slips, pph21_paid_jan_nov=0):
    """
    Hitung PPh 21 progressive/normal (Desember/final year) berdasarkan list
    salary slip sepanjang tahun.

    Args:
        employee: dict/Document Employee (punya tax_status dan employment_type)
        salary_slips: list of dict/Document Salary Slip untuk satu tahun penuh
        pph21_paid_jan_nov: float, total PPh21 yang sudah dibayar Januari-November

    Returns:
        dict dengan keys sama seperti :func:`calculate_pph21_TER_december_from_annual_payroll`.
    """

    employment_type = None
    tax_status = None
    if hasattr(employee, "employment_type"):
        employment_type = getattr(employee, "employment_type")
        tax_status = getattr(employee, "tax_status", None)
    elif isinstance(employee, dict):
        employment_type = employee.get("employment_type")
        tax_status = employee.get("tax_status")

    if employment_type != "Full-time":
        return {
            "bruto_total": 0.0,
            "netto_total": 0.0,
            "ptkp_annual": 0.0,
            "pkp_annual": 0.0,
            "rate": "",
            "pph21_annual": 0.0,
            "pph21_month": 0.0,
            "income_tax_deduction_total": 0.0,
            "biaya_jabatan_total": 0.0,
            "koreksi_pph21": 0.0,
            "employment_type_checked": False,
            "message": "PPh21 TER Desember hanya dihitung untuk Employment Type: Full-time",
        }

    if not salary_slips:
        return {"message": "Daftar salary slip kosong.", "employment_type_checked": True}

    bruto_total = 0.0
    pengurang_netto_total = 0.0
    biaya_jabatan_total = 0.0

    for slip in salary_slips:
        bruto_total += sum_bruto_earnings(slip)
        pengurang_netto_total += sum_income_tax_deductions(slip)
        biaya_jabatan_total += get_biaya_jabatan_from_component(slip)

    netto_total = bruto_total - pengurang_netto_total - biaya_jabatan_total

    ptkp_annual = get_ptkp_amount(tax_status)
    pkp_annual = calculate_pkp_annual(netto_total, ptkp_annual)
    pph21_annual = calculate_pph21_progressive(pkp_annual)
    koreksi_pph21 = pph21_annual - pph21_paid_jan_nov
    pph21_month_des = koreksi_pph21 if koreksi_pph21 > 0 else 0
    rates = "/".join([f"{rate}%" for _, rate in get_tax_slabs()])

    return {
        "bruto_total": bruto_total,
        "netto_total": netto_total,
        "ptkp_annual": ptkp_annual,
        "pkp_annual": pkp_annual,
        "rate": rates,
        "pph21_annual": pph21_annual,
        "pph21_month": pph21_month_des,
        "income_tax_deduction_total": pengurang_netto_total,
        "biaya_jabatan_total": biaya_jabatan_total,
        "koreksi_pph21": koreksi_pph21,
        "employment_type_checked": True,
    }

def calculate_pph21_TER_december_from_annual_payroll(annual_payroll_history, employee=None):
    """
    Hitung PPh 21 progressive/normal (Desember/final year) berdasarkan data Annual Payroll History (parent dan child).
    Hanya untuk Employment Type: Full-time.

    Args:
        annual_payroll_history: Document/Dict AnnualPayrollHistory, memuat child table (monthly details)
        employee: optional, Document/Dict Employee jika ingin override (default ambil dari parent)

    Returns:
        dict: {
            'bruto_total': float,
            'netto_total': float,
            'ptkp_annual': float,
            'pkp_annual': float,
            'rate': str,       # range progresif
            'pph21_annual': float,
            'pph21_month': float,
            'income_tax_deduction_total': float,
            'biaya_jabatan_total': float,
            'koreksi_pph21': float,
            'employment_type_checked': bool,
            'message': str (optional)
        }
    """

    # Ambil data employee dari parent jika tidak diberikan
    if not employee:
        employee = getattr(annual_payroll_history, "employee", None) or getattr(annual_payroll_history, "employee_doc", None)
        if hasattr(annual_payroll_history, "as_dict"):
            employee = annual_payroll_history.as_dict().get("employee") or annual_payroll_history.as_dict().get("employee_doc")

    # Cek employment type Full-time
    employment_type = None
    tax_status = None
    if hasattr(employee, "employment_type"):
        employment_type = getattr(employee, "employment_type")
        tax_status = getattr(employee, "tax_status", None)
    elif isinstance(employee, dict):
        employment_type = employee.get("employment_type")
        tax_status = employee.get("tax_status")

    if employment_type != "Full-time":
        return {
            "bruto_total": 0.0,
            "netto_total": 0.0,
            "ptkp_annual": 0.0,
            "pkp_annual": 0.0,
            "rate": "",
            "pph21_annual": 0.0,
            "pph21_month": 0.0,
            "income_tax_deduction_total": 0.0,
            "biaya_jabatan_total": 0.0,
            "koreksi_pph21": 0.0,
            "employment_type_checked": False,
            "message": "PPh21 TER Desember hanya dihitung untuk Employment Type: Full-time"
        }

    # --- Ambil data dari parent & child table ---
    # Child table bisa: .monthly_details atau .annual_payroll_history_childs
    child_table = getattr(annual_payroll_history, "monthly_details", None) \
        or getattr(annual_payroll_history, "annual_payroll_history_childs", None) \
        or annual_payroll_history.get("monthly_details") \
        or annual_payroll_history.get("annual_payroll_history_childs")

    if not child_table or len(child_table) == 0:
        return {
            "message": "Data child (detail bulan) tidak ditemukan.",
            "employment_type_checked": True
        }

    # Sum seluruh tahun
    bruto_total = 0.0
    pengurang_netto_total = 0.0
    biaya_jabatan_total = 0.0
    netto_total = 0.0
    pkp_total = 0.0
    pph21_total = 0.0

    # Untuk total PPh21 Jan–Nov
    pph21_paid_jan_nov = 0.0

    for row in child_table:
        bulan = None
        if hasattr(row, "bulan"):
            bulan = getattr(row, "bulan")
        elif isinstance(row, dict):
            bulan = row.get("bulan")
        bruto = getattr(row, "bruto", None) if hasattr(row, "bruto") else row.get("bruto", 0)
        pengurang_netto = getattr(row, "pengurang_netto", None) if hasattr(row, "pengurang_netto") else row.get("pengurang_netto", 0)
        biaya_jabatan = getattr(row, "biaya_jabatan", None) if hasattr(row, "biaya_jabatan") else row.get("biaya_jabatan", 0)
        netto = getattr(row, "netto", None) if hasattr(row, "netto") else row.get("netto", 0)
        pkp = getattr(row, "pkp", None) if hasattr(row, "pkp") else row.get("pkp", 0)
        pph21 = getattr(row, "pph21", None) if hasattr(row, "pph21") else row.get("pph21", 0)

        bruto_total += float(bruto or 0)
        pengurang_netto_total += float(pengurang_netto or 0)
        biaya_jabatan_total += float(biaya_jabatan or 0)
        netto_total += float(netto or 0)
        pkp_total += float(pkp or 0)
        pph21_total += float(pph21 or 0)

        # Jan–Nov only (bulan 1 s.d. 11)
        if bulan and int(bulan) < 12:
            pph21_paid_jan_nov += float(pph21 or 0)

    # --- Perhitungan PPh21 Desember ---
    # PTKP tahunan

    ptkp_annual = get_ptkp_amount(tax_status)
    pkp_annual = calculate_pkp_annual(netto_total, ptkp_annual)
    pph21_annual = calculate_pph21_progressive(pkp_annual)
    koreksi_pph21 = pph21_annual - pph21_paid_jan_nov
    pph21_month_des = koreksi_pph21 if koreksi_pph21 > 0 else 0
    rates = "/".join([f"{rate}%" for _, rate in get_tax_slabs()])

    return {
        "bruto_total": bruto_total,
        "netto_total": netto_total,
        "ptkp_annual": ptkp_annual,
        "pkp_annual": pkp_annual,
        "rate": rates,
        "pph21_annual": pph21_annual,
        "pph21_month": pph21_month_des,
        "income_tax_deduction_total": pengurang_netto_total,
        "biaya_jabatan_total": biaya_jabatan_total,
        "koreksi_pph21": koreksi_pph21,
        "employment_type_checked": True,
    }
