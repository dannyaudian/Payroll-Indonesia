import frappe
from frappe.utils import flt
from payroll_indonesia.config import config

def get_ter_code(tax_status):
    """Ambil kode TER dari tax_status via settings/mapping table."""
    settings = config.get_settings()
    for row in settings.get("ter_mapping_table", []):
        if row.tax_status == tax_status:
            return row.ter_code
    return None

def get_ter_rate(ter_code, monthly_income):
    """Cari rate TER (%) untuk kode dan penghasilan tertentu dari tabel setting."""
    settings = config.get_settings()
    brackets = [b for b in settings.get("ter_bracket_table", []) if b.ter_code == ter_code]
    for row in brackets:
        min_income = flt(row.min_income or 0)
        max_income = flt(row.max_income or 0)
        rate = flt(row.rate_percent or 0)
        if monthly_income >= min_income and (max_income == 0 or monthly_income <= max_income):
            return rate
    return 0.0

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

def calculate_pph21_TER(employee, salary_slip):
    """
    Hitung PPh 21 metode TER per bulan (PMK 168/2023) berbasis flag salary component, tanpa hardcode nama komponen.

    Args:
        employee: dict atau doc Employee (wajib punya tax_status)
        salary_slip: dict, wajib ada earnings dan deductions (list of dicts)
    Returns:
        dict: {
            'bruto': float,
            'netto': float,
            'ptkp': float,
            'pkp': float,
            'rate': float,
            'pph21': float,
            'income_tax_deduction': float,
            'biaya_jabatan': float,
        }
    """
    # 1. Hitung bruto: earning taxable (flag sesuai salary component)
    bruto = sum_taxable_earnings(salary_slip)

    # 2. Pengurang: deduction yang relevan untuk PPh 21 (BPJS employee dll, sesuai flag)
    income_tax_deduction = sum_income_tax_deductions(salary_slip)

    # 3. Biaya jabatan
    biaya_jabatan = calculate_biaya_jabatan(bruto)

    # 4. Netto
    netto = bruto - income_tax_deduction - biaya_jabatan

    # 5. PTKP (per bulan)
    tax_status = getattr(employee, "tax_status", None) if hasattr(employee, "tax_status") else employee.get("tax_status")
    ptkp = get_ptkp_amount(tax_status) / 12

    # 6. PKP (bulanan)
    pkp = max(netto - ptkp, 0)

    # 7. Cari kode TER
    ter_code = get_ter_code(tax_status)
    # 8. Cari tarif TER
    rate = get_ter_rate(ter_code, pkp)

    # 9. Hitung PPh 21
    pph21 = round(pkp * rate / 100)

    return {
        "bruto": bruto,
        "netto": netto,
        "ptkp": ptkp,
        "pkp": pkp,
        "rate": rate,
        "pph21": pph21,
        "income_tax_deduction": income_tax_deduction,
        "biaya_jabatan": biaya_jabatan,
    }