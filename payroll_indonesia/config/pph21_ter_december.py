"""
PPh21 December Progressive (Annual Correction) calculation module.

This module handles the December/annual income tax correction calculation
for Indonesian payroll using the progressive tax rates. It ONLY handles
December calculations, not regular monthly TER calculations.

IMPORTANT: This module only handles December/annual calculations.
           Regular monthly calculations must use pph21_ter.py
"""

import frappe
from frappe import ValidationError
from frappe.utils import flt
from typing import Dict, Any, List, Union, Tuple, Optional

# Import from config (not from other calculation modules to avoid circular imports)
from payroll_indonesia.config import get_ptkp_amount, config

# Default progressive slabs (PMK 168/2023, berlaku 2024)
DEFAULT_TAX_SLABS = [
    (60_000_000, 5),
    (250_000_000, 15),
    (500_000_000, 25),
    (5_000_000_000, 30),
    (float("inf"), 35),
]

def calculate_pph21_december(
    taxable_income: float,
    employee: Union[Dict[str, Any], Any],
    company: str,
    ytd_income: float,
    ytd_tax_paid: float
) -> Dict[str, Any]:
    """
    Calculate December PPh21 using progressive rates (annual correction).
    
    Args:
        taxable_income: Pendapatan kena pajak bulan Desember
        employee: Employee document or dictionary with employee data
        company: Company name or ID
        ytd_income: Year-to-date income including December
        ytd_tax_paid: Year-to-date tax paid from January-November
        
    Returns:
        Dictionary with calculation results including December PPh21 amount
        
    Raises:
        frappe.ValidationError: For validation errors in input data
    """
    # Input validation
    if not employee:
        frappe.throw("Employee data is required for PPh21 calculation", title="Missing Employee")
        
    if not company:
        frappe.throw("Company is required for PPh21 calculation", title="Missing Company")
    
    # Employment type check
    emp_type = employee.get("employment_type") if isinstance(employee, dict) else getattr(employee, "employment_type", None)
    if emp_type != "Full-time":
        return {
            "bruto_total": ytd_income,
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
            "message": "PPh21 December hanya dihitung untuk Employment Type: Full-time"
        }
    
    # Get PTKP annual amount
    try:
        ptkp_annual = get_ptkp_amount(employee)
    except ValidationError as e:
        frappe.logger().warning(str(e))
        ptkp_annual = 0.0
    
    # Calculate PKP (annual taxable income)
    pkp_annual = calculate_pkp_annual(ytd_income, ptkp_annual)
    
    # Calculate annual PPh21 using progressive rates
    pph21_annual = calculate_pph21_progressive(pkp_annual)

    # Calculate correction for December
    koreksi_pph21 = pph21_annual - ytd_tax_paid

    frappe.logger().debug(
        "December PPh21 calculation: pph21_annual=%s, ytd_tax_paid=%s, koreksi_pph21=%s",
        pph21_annual,
        ytd_tax_paid,
        koreksi_pph21,
    )

    # December PPh21 is the positive correction amount (negative means refund, handled separately)
    pph21_bulan_des = max(0, koreksi_pph21)
    
    # Get tax rates description
    rates = "/".join([f"{rate}%" for _, rate in get_tax_slabs()])
    
    # Prepare result
    result = {
        "bruto_total": ytd_income,
        "netto_total": ytd_income,  # Simplified - proper netto would include deductions
        "ptkp_annual": ptkp_annual,
        "pkp_annual": pkp_annual,
        "rate": rates,
        "pph21_annual": pph21_annual,
        "pph21_bulan": pph21_bulan_des,
        "income_tax_deduction_total": 0.0,  # Would need actual deduction data
        "biaya_jabatan_total": 0.0,  # Would need actual biaya jabatan data
        "koreksi_pph21": koreksi_pph21,
        "employment_type_checked": True,
    }
    
    return result

def calculate_pph21_december_from_slips(
    employee: Union[Dict[str, Any], Any],
    company: str,
    salary_slips: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculate December PPh21 using data from all salary slips in the year.
    
    Args:
        employee: Employee document or dictionary with employee data
        company: Company name or ID
        salary_slips: List of salary slip dictionaries for the entire year
        
    Returns:
        Dictionary with calculation results including December PPh21 amount
        
    Raises:
        frappe.ValidationError: For validation errors in input data
    """
    # Input validation
    if not employee:
        frappe.throw("Employee data is required for PPh21 calculation", title="Missing Employee")
        
    if not company:
        frappe.throw("Company is required for PPh21 calculation", title="Missing Company")
    
    if not salary_slips:
        return {"message": "Daftar salary slip kosong.", "employment_type_checked": True}
    
    # Employment type check
    emp_type = employee.get("employment_type") if isinstance(employee, dict) else getattr(employee, "employment_type", None)
    if emp_type != "Full-time":
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
            "message": "PPh21 December hanya dihitung untuk Employment Type: Full-time"
        }
    
    # Process all slips to calculate totals
    bruto_total = 0.0
    pengurang_netto_total = 0.0
    biaya_jabatan_total = 0.0
    pph21_paid_jan_nov = 0.0
    
    # Pisahkan slip bulan Desember jika ada
    december_slip = None
    jan_nov_slips = []

    for slip in salary_slips:
        # Coba tentukan bulan dari tanggal mulai
        bulan = None
        if slip.get("start_date"):
            try:
                from frappe.utils import getdate
                bulan = getdate(slip.get("start_date")).month
            except Exception:
                pass

        # Jika teridentifikasi bulan 12, pisahkan
        if bulan == 12:
            december_slip = slip
            continue

        # Tambahkan ke daftar Jan-Nov
        jan_nov_slips.append(slip)
        
        # Process Jan-Nov slips for totals
        bruto_total += sum_bruto_earnings(slip)
        pengurang_netto_total += sum_income_tax_deductions(slip)
        biaya_jabatan_total += get_biaya_jabatan_from_component(slip)
        pph21_paid_jan_nov += flt(slip.get("tax", 0.0))
    
    # Add December amounts if available
    if december_slip:
        bruto_total += sum_bruto_earnings(december_slip)
        pengurang_netto_total += sum_income_tax_deductions(december_slip)
        biaya_jabatan_total += get_biaya_jabatan_from_component(december_slip)
    
    # Calculate netto
    netto_total = bruto_total - pengurang_netto_total - biaya_jabatan_total
    
    # Get PTKP annual amount
    try:
        ptkp_annual = get_ptkp_amount(employee)
    except ValidationError as e:
        frappe.logger().warning(str(e))
        ptkp_annual = 0.0
    
    # Calculate PKP
    pkp_annual = calculate_pkp_annual(netto_total, ptkp_annual)
    
    # Calculate annual PPh21
    pph21_annual = calculate_pph21_progressive(pkp_annual)
    
    # Calculate correction
    koreksi_pph21 = pph21_annual - pph21_paid_jan_nov
    
    # December PPh21
    pph21_bulan_des = koreksi_pph21 if koreksi_pph21 > 0 else 0
    
    # Get tax rates description
    rates = "/".join([f"{rate}%" for _, rate in get_tax_slabs()])
    
    # Prepare result
    result = {
        "bruto_total": bruto_total,
        "netto_total": netto_total,
        "ptkp_annual": ptkp_annual,
        "pkp_annual": pkp_annual,
        "rate": rates,
        "pph21_annual": pph21_annual,
        "pph21_bulan": pph21_bulan_des,
        "income_tax_deduction_total": pengurang_netto_total,
        "biaya_jabatan_total": biaya_jabatan_total,
        "koreksi_pph21": koreksi_pph21,
        "employment_type_checked": True,
    }
    
    return result

def get_tax_slabs() -> List[Tuple[float, float]]:
    """
    Get progressive tax slabs from Income Tax Slab doctype, or fallback to default.
    
    Returns:
        List of tuples (income_limit, tax_rate_percent)
    """
    slab_name = config.get_value("fallback_income_tax_slab")
    if not slab_name:
        return DEFAULT_TAX_SLABS

    try:
        slab_doc = frappe.get_cached_doc("Income Tax Slab", slab_name)
    except Exception:
        frappe.logger().warning(f"Income Tax Slab {slab_name} tidak ditemukan")
        return DEFAULT_TAX_SLABS

    slabs = []
    for row in slab_doc.get("slabs", []):
        batas = flt(row.get("to_amount", 0))
        if batas == 0:
            batas = float("inf")
        rate = flt(row.get("percent_deduction", 0))
        slabs.append((batas, rate))

    if not slabs:
        return DEFAULT_TAX_SLABS

    slabs.sort(key=lambda x: x[0])
    return slabs

def sum_bruto_earnings(salary_slip: Dict[str, Any]) -> float:
    """
    Sum all taxable earning components for bruto (including natura taxable).
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
            total += flt(row.get("amount", 0))
    return total

def sum_income_tax_deductions(salary_slip: Dict[str, Any]) -> float:
    """
    Sum all deductions for netto, EXCLUDE biaya jabatan.
    """
    total = 0.0
    for row in salary_slip.get("deductions", []):
        if (
            (row.get("is_income_tax_component", 0) == 1 or 
             row.get("variable_based_on_taxable_salary", 0) == 1 or
             row.get("is_pengurang_netto", 0) == 1)
            and row.get("do_not_include_in_total", 0) == 0
            and row.get("statistical_component", 0) == 0
            and "biaya jabatan" not in row.get("salary_component", "").lower()
        ):
            total += flt(row.get("amount", 0))
    return total

def get_biaya_jabatan_from_component(salary_slip: Dict[str, Any]) -> float:
    """
    Get 'Biaya Jabatan' deduction from salary slip, return 0 if not present.
    """
    for row in salary_slip.get("deductions", []):
        if "biaya jabatan" in row.get("salary_component", "").lower():
            return flt(row.get("amount", 0))
    return 0.0

def calculate_pkp_annual(total_netto_actual: float, ptkp_annual: float) -> float:
    """
    PKP annual = (total netto setahun - PTKP setahun), rounded to nearest 1000.
    """
    pkp = max(total_netto_actual - ptkp_annual, 0)
    return int(round(pkp / 1000.0)) * 1000

def calculate_pph21_progressive(pkp_annual: float) -> float:
    """
    Calculate annual PPh21 using progressive slabs.
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