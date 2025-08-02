import frappe
from frappe.utils import flt
from payroll_indonesia.config import config

# Default progressive tax slabs PMK 168/2023 (berlaku 2024)
DEFAULT_TAX_SLABS = [
    (60_000_000, 5),
    (250_000_000, 15),
    (500_000_000, 25),
    (5_000_000_000, 30),
    (float("inf"), 35),
]

def get_tax_slabs():
    """Ambil daftar tax slab dari dokumen Income Tax Slab di settings, fallback ke DEFAULT_TAX_SLABS."""
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

def calculate_pkp_annual(netto_total, ptkp_annual):
    """
    PKP tahunan = (total netto setahun - PTKP setahun), dibulatkan ke ribuan terdekat.
    """
    pkp = max(netto_total - ptkp_annual, 0)
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

def calculate_pph21_progressive_year(employee, salary_slips, pph21_paid_jan_nov=0):
    """
    Hitung PPh 21 progressive/normal (Desember/final year) berdasarkan income tax slab.
    Hanya untuk Employment Type: Full-time.

    Args:
        employee: dict atau doc Employee (punya tax_status dan employment_type)
        salary_slips: list of dict, slip seluruh tahun berjalan (Jan–Des)
        pph21_paid_jan_nov: float, total PPh21 yang sudah dipotong/dibayar Jan–Nov

    Returns:
        dict: {
            'bruto_total': float,
            'netto_total': float,
            'ptkp_annual': float,
            'pkp_annual': float,
            'rate': str,       # range progresif
            'pph21_annual': float,
            'pph21_bulan': float,
            'income_tax_deduction_total': float,
            'biaya_jabatan_total': float,
            'koreksi_pph21': float,
            'employment_type_checked': bool
        }
    """
    employment_type = None
    if hasattr(employee, "employment_type"):
        employment_type = getattr(employee, "employment_type")
    elif isinstance(employee, dict):
        employment_type = employee.get("employment_type")

    if employment_type != "Full-time":
        return {
            "bruto_total": 0.0,
            "netto_total": 0.0,
            "ptkp_annual": 0.0,
            "pkp_annual": 0.0,
            "rate": "",
            "pph21_annual": 0.0,
            "pph21_bulan": 0.0,
            "income_tax_deduction_total": 0.0,
            "biaya_jabatan_total": 0.0,
            "koreksi_pph21": 0.0,
            "employment_type_checked": False,
            "message": "PPh21 Progressive hanya dihitung untuk Employment Type: Full-time"
        }

    # 1. PTKP tahunan
    tax_status = getattr(employee, "tax_status", None) if hasattr(employee, "tax_status") else employee.get("tax_status")
    ptkp_annual = get_ptkp_amount(tax_status)

    # 2. Jumlah slip gaji tahun berjalan (Jan–Des)
    bruto_total = 0.0
    income_tax_deduction_total = 0.0
    biaya_jabatan_total = 0.0
    netto_total = 0.0

    for slip in salary_slips:
        bruto = sum_bruto_earnings(slip)
        pengurang_netto = sum_income_tax_deductions(slip)
        biaya_jabatan = get_biaya_jabatan_from_component(slip)
        netto = bruto - pengurang_netto - biaya_jabatan
        bruto_total += bruto
        income_tax_deduction_total += pengurang_netto
        biaya_jabatan_total += biaya_jabatan
        netto_total += netto

    # 3. PKP tahunan
    pkp_annual = calculate_pkp_annual(netto_total, ptkp_annual)

    # 4. Hitung PPh progresif setahun
    pph21_annual = calculate_pph21_progressive(pkp_annual)
    # 5. Pajak bulan Desember/final
    koreksi_pph21 = pph21_annual - pph21_paid_jan_nov
    if koreksi_pph21 > 0:
        pph21_bulan = koreksi_pph21
    else:
        pph21_bulan = 0

    # 6. Rate info (for audit only)
    rates = "/".join([f"{rate}%" for _, rate in get_tax_slabs()])

    return {
        "bruto_total": bruto_total,
        "netto_total": netto_total,
        "ptkp_annual": ptkp_annual,
        "pkp_annual": pkp_annual,
        "rate": rates,
        "pph21_annual": pph21_annual,
        "pph21_bulan": pph21_bulan,
        "income_tax_deduction_total": income_tax_deduction_total,
        "biaya_jabatan_total": biaya_jabatan_total,
        "koreksi_pph21": koreksi_pph21,
        "employment_type_checked": True
    }