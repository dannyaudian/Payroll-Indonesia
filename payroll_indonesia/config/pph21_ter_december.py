import frappe
from frappe.utils import flt
from payroll_indonesia.config import config

# Income tax slab untuk progressive (PMK 168/2023, berlaku 2024)
# Data bawaan digunakan jika dokumen Income Tax Slab tidak ditemukan.
DEFAULT_TAX_SLABS = [
    # (batas_atas, tarif_persen)
    (60_000_000, 5),
    (250_000_000, 15),
    (500_000_000, 25),
    (5_000_000_000, 30),
    (float("inf"), 35),
]


def get_tax_slabs() -> list[tuple[float, float]]:
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

def get_ptkp_amount(tax_status):
    """Ambil PTKP dari table di settings."""
    settings = config.get_settings()
    for row in settings.get("ptkp_table", []):
        if row.tax_status == tax_status:
            return flt(row.ptkp_amount)
    return 0.0

def sum_taxable_earnings(salary_slip):
    """
    Menjumlahkan earning taxable sesuai setting komponen salary:
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
    Menjumlahkan deduction yang harus menjadi pengurang netto pada perhitungan PPh 21.
    Contoh: BPJS Kesehatan Employee, BPJS JHT Employee, BPJS JP Employee,
    sesuai dengan flag (is_income_tax_component = 1 atau variable_based_on_taxable_salary = 1 pada deduction).
    """
    total = 0.0
    for row in salary_slip.get("deductions", []):
        if (
            (row.get("is_income_tax_component", 0) == 1 or
             row.get("variable_based_on_taxable_salary", 0) == 1)
            and row.get("do_not_include_in_total", 0) == 0
            and row.get("statistical_component", 0) == 0
        ):
            total += flt(row.amount)
    return total

def calculate_biaya_jabatan(bruto):
    """Hitung biaya jabatan: 5% bruto, maksimal 500.000/bulan."""
    return min(bruto * 0.05, 500_000)

def calculate_pkp_annual(netto_bulanan, ptkp_bulanan):
    """PKP tahunan = (netto bulanan - PTKP bulanan) * 12, dibulatkan ke ribuan terdekat"""
    pkp = max((netto_bulanan - ptkp_bulanan) * 12, 0)
    # pembulatan ke ribuan
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

def calculate_pph21_TER_december(employee, salary_slip):
    """
    Hitung PPh 21 metode progressive/normal (Desember/final year) berdasarkan income tax slab.

    Args:
        employee: dict atau doc Employee (wajib punya tax_status)
        salary_slip: dict, wajib ada earnings dan deductions (list of dicts)
    Returns:
        dict: {
            'bruto': float,
            'netto': float,
            'ptkp': float,
            'pkp_annual': float,
            'rate': str,       # range progresif
            'pph21_annual': float,
            'pph21_month': float,
            'income_tax_deduction': float,
            'biaya_jabatan': float,
        }
    """
    # 1. Bruto taxable earning
    bruto = sum_taxable_earnings(salary_slip)
    # 2. Pengurang: deduction (BPJS employee, dll, sesuai flag)
    income_tax_deduction = sum_income_tax_deductions(salary_slip)
    # 3. Biaya Jabatan
    biaya_jabatan = calculate_biaya_jabatan(bruto)
    # 4. Netto bulanan
    netto = bruto - income_tax_deduction - biaya_jabatan
    # 5. PTKP bulanan
    tax_status = getattr(employee, "tax_status", None) if hasattr(employee, "tax_status") else employee.get("tax_status")
    ptkp = get_ptkp_amount(tax_status)
    ptkp_bulanan = ptkp / 12
    # 6. PKP tahunan
    pkp_annual = calculate_pkp_annual(netto, ptkp_bulanan)
    # 7. Hitung PPh progresif setahun
    pph21_annual = calculate_pph21_progressive(pkp_annual)
    # 8. Pajak bulan Desember/final
    pph21_month = round(pph21_annual - getattr(employee, "pph21_paid_jan_nov", 0))
    # 9. Rate info (for audit only)
    rates = "/".join([f"{rate}%" for _, rate in get_tax_slabs()])
    return {
        "bruto": bruto,
        "netto": netto,
        "ptkp": ptkp,
        "pkp_annual": pkp_annual,
        "rate": rates,
        "pph21_annual": pph21_annual,
        "pph21_month": pph21_month,
        "income_tax_deduction": income_tax_deduction,
        "biaya_jabatan": biaya_jabatan,
    }