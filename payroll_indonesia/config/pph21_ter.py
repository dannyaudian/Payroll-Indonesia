import frappe
from frappe import ValidationError
from frappe.utils import flt
from payroll_indonesia.config import (
    get_ptkp_amount,
    get_ter_code,
    get_ter_rate
)

def sum_bruto_earnings(salary_slip):
    """
    Sum all earning components contributing to bruto pay (including taxable natura).
    Criteria:
      - is_tax_applicable = 1
      - OR is_income_tax_component = 1
      - OR variable_based_on_taxable_salary = 1
      - do_not_include_in_total = 0
      - statistical_component = 0
      - exempted_from_income_tax = 0 (if field exists)
    """
    total = 0.0
    earnings = salary_slip.get("earnings", [])
    for row in earnings:
        if (
            (row.get("is_tax_applicable", 0) == 1 or
             row.get("is_income_tax_component", 0) == 1 or
             row.get("variable_based_on_taxable_salary", 0) == 1)
            and row.get("do_not_include_in_total", 0) == 0
            and row.get("statistical_component", 0) == 0
            and row.get("exempted_from_income_tax", 0) == 0
        ):
            total += flt(row.get("amount", 0))
    return total

def sum_pengurang_netto(salary_slip):
    """
    Sum deductions that reduce netto (BPJS Employee etc).
    Criteria:
      - is_income_tax_component = 1 OR variable_based_on_taxable_salary = 1
      - do_not_include_in_total = 0
      - statistical_component = 0
      - Exclude 'Biaya Jabatan'
    """
    total = 0.0
    deductions = salary_slip.get("deductions", [])
    for row in deductions:
        if (
            (row.get("is_income_tax_component", 0) == 1 or row.get("variable_based_on_taxable_salary", 0) == 1)
            and row.get("do_not_include_in_total", 0) == 0
            and row.get("statistical_component", 0) == 0
            and "biaya jabatan" not in row.get("salary_component", "").lower()
        ):
            total += flt(row.get("amount", 0))
    return total

def get_biaya_jabatan_from_component(salary_slip):
    """
    Get 'Biaya Jabatan' deduction from salary slip, return 0 if not present.
    """
    deductions = salary_slip.get("deductions", [])
    for row in deductions:
        if "biaya jabatan" in row.get("salary_component", "").lower():
            return flt(row.get("amount", 0))
    return 0.0

def calculate_pph21_TER(employee_doc, salary_slip):
    """
    Calculate PPh21 TER logic for Indonesian payroll.

    Args:
        employee_doc: Employee Doc/dict with 'tax_status' and 'employment_type'
        salary_slip: dict, must contain earnings and deductions (list of dicts)

    Returns:
        dict:
            'ptkp': float,
            'bruto': float,
            'pengurang_netto': float,
            'biaya_jabatan': float,
            'netto': float,
            'pkp': float,
            'rate': float,
            'pph21': float,
            'employment_type_checked': bool,
            'message': str (if not eligible)
    """
    # Employment type check
    employment_type = getattr(employee_doc, "employment_type", None) \
        if hasattr(employee_doc, "employment_type") else employee_doc.get("employment_type")
    if employment_type != "Full-time":
        return {
            "ptkp": 0.0,
            "bruto": 0.0,
            "pengurang_netto": 0.0,
            "biaya_jabatan": 0.0,
            "netto": 0.0,
            "pkp": 0.0,
            "rate": 0.0,
            "pph21": 0.0,
            "employment_type_checked": False,
            "message": "PPh21 TER hanya dihitung untuk Employment Type: Full-time"
        }

    # PTKP bulanan
    try:
        ptkp = get_ptkp_amount(employee_doc) / 12
    except ValidationError as e:
        frappe.logger().warning(str(e))
        ptkp = 0.0

    # Earnings: penghasilan bruto (termasuk natura taxable)
    bruto = sum_bruto_earnings(salary_slip)

    # Deductions: pengurang netto (exclude biaya jabatan)
    pengurang_netto = sum_pengurang_netto(salary_slip)

    # Biaya Jabatan dari komponen deduction "Biaya Jabatan"
    biaya_jabatan = get_biaya_jabatan_from_component(salary_slip)

    # Netto
    netto = bruto - pengurang_netto - biaya_jabatan

    # PKP (bulanan)
    pkp = max(netto - ptkp, 0)

    # TER code & rate
    ter_code = get_ter_code(employee_doc)
    try:
        rate = get_ter_rate(ter_code, pkp)
    except ValidationError as e:
        frappe.logger().warning(str(e))
        rate = 0.0
    frappe.logger().info(f"TER code: {ter_code}, rate: {rate}")

    # PPh21
    pph21 = round(pkp * (rate / 100))

    return {
        "ptkp": ptkp,
        "bruto": bruto,
        "pengurang_netto": pengurang_netto,
        "biaya_jabatan": biaya_jabatan,
        "netto": netto,
        "pkp": pkp,
        "rate": rate,
        "pph21": pph21,
        "employment_type_checked": True
    }