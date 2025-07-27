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

def sum_bruto_earnings(salary_slip):
    """
    Menjumlahkan seluruh komponen earning yang menambah penghasilan bruto:
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

def sum_natura_earnings(salary_slip):
    """
    Menjumlahkan earning natura yang dikenakan pajak (natura taxable):
    - is_tax_applicable = 1
    - do_not_include_in_total = 0
    - statistical_component = 0
    - exempted_from_income_tax = 0
    - (pastikan komponen natura taxable mengisi flag dengan benar di salary_component.json)
    """
    total = 0.0
    for row in salary_slip.get("earnings", []):
        if (
            row.get("is_tax_applicable", 0) == 1
            and row.get("do_not_include_in_total", 0) == 0
            and row.get("statistical_component", 0) == 0
            and row.get("exempted_from_income_tax", 0) == 0
            and "natura" in (row.get("description", "").lower() + row.get("salary_component", "").lower())
        ):
            total += flt(row.amount)
    return total

def sum_pengurang_netto(salary_slip):
    """
    Menjumlahkan deduction pengurang netto (BPJS Kesehatan Employee, BPJS JHT Employee, BPJS JP Employee, dsb)
    - is_income_tax_component = 1 atau variable_based_on_taxable_salary = 1
    - do_not_include_in_total = 0
    - statistical_component = 0
    - exclude biaya jabatan!
    """
    total = 0.0
    for row in salary_slip.get("deductions", []):
        if (
            (row.get("is_income_tax_component", 0) == 1 or row.get("variable_based_on_taxable_salary", 0) == 1)
            and row.get("do_not_include_in_total", 0) == 0
            and row.get("statistical_component", 0) == 0
            and "biaya jabatan" not in row.get("salary_component", "").lower()
        ):
            total += flt(row.amount)
    return total

def sum_biaya_jabatan(salary_slip, bruto):
    """
    Mengambil nilai biaya jabatan dari deduction (jika ada), 
    jika tidak ada hitung manual 5% maksimal 500.000.
    """
    for row in salary_slip.get("deductions", []):
        if "biaya jabatan" in row.get("salary_component", "").lower():
            return flt(row.amount)
    # fallback: hitung manual jika tidak ditemukan
    return min(bruto * 0.05, 500_000)

def calculate_pph21_TER(employee, salary_slip):
    """
    Hitung PPh 21 metode TER per bulan (PMK 168/2023) dengan pemisahan rumus:
      - PTKP
      - Penghasilan Bruto (termasuk natura)
      - Pengurang Netto (exclude biaya jabatan)
      - Biaya Jabatan
      - PKP

    Args:
        employee: dict atau doc Employee (wajib punya tax_status)
        salary_slip: dict, wajib ada earnings dan deductions (list of dicts)
    Returns:
        dict: {
            'ptkp': float,
            'bruto': float,
            'pengurang_netto': float,
            'biaya_jabatan': float,
            'netto': float,
            'pkp': float,
            'rate': float,
            'pph21': float,
        }
    """
    # 1. PTKP bulanan
    tax_status = getattr(employee, "tax_status", None) if hasattr(employee, "tax_status") else employee.get("tax_status")
    ptkp = get_ptkp_amount(tax_status) / 12

    # 2. Penghasilan Bruto (termasuk natura taxable)
    bruto = sum_bruto_earnings(salary_slip)

    # 3. Pengurang Netto (exclude biaya jabatan)
    pengurang_netto = sum_pengurang_netto(salary_slip)

    # 4. Biaya Jabatan
    biaya_jabatan = sum_biaya_jabatan(salary_slip, bruto)

    # 5. Netto
    netto = bruto - pengurang_netto - biaya_jabatan

    # 6. PKP (bulanan)
    pkp = max(netto - ptkp, 0)

    # 7. Cari kode TER & rate
    ter_code = get_ter_code(tax_status)
    rate = get_ter_rate(ter_code, pkp)

    # 8. Hitung PPh 21
    pph21 = round(pkp * rate / 100)

    return {
        "ptkp": ptkp,
        "bruto": bruto,
        "pengurang_netto": pengurang_netto,
        "biaya_jabatan": biaya_jabatan,
        "netto": netto,
        "pkp": pkp,
        "rate": rate,
        "pph21": pph21,
    }