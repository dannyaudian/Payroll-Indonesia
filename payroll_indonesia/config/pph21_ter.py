"""
PPh21 TER (Tabel Pajak Bulanan) calculation module.

This module handles the monthly income tax calculation for Indonesian payroll.
It uses the TER method (monthly table) for tax calculation.

IMPORTANT: This module only handles monthly TER calculations.
           December/annual calculations must use pph21_ter_december.py
"""

import frappe
from frappe import ValidationError
from frappe.utils import flt
from typing import Dict, Any, Optional, Union, List

# Prevent circular imports - only import config constants
from payroll_indonesia.config import (
    get_ptkp_amount,
    get_ter_code,
    get_ter_rate,
    get_biaya_jabatan_rate,
    get_biaya_jabatan_cap_monthly,
)
from payroll_indonesia.utils import round_half_up

# Constants for component identification
PENGURANG_NETTO_NAMES = {
    "bpjs kesehatan employee",   # 1% karyawan
    "bpjs jht employee",         # 2% karyawan
    "bpjs jp employee",          # 1% karyawan
    # tambahkan jika ada iuran pensiun lain:
    "iuran pensiun",
    "dana pensiun",
}

def calculate_pph21_TER(taxable_income: Union[float, Dict[str, Any]],
                        employee: Union[Dict[str, Any], Any],
                        company: str,
                        bulan: int = None) -> Dict[str, Any]:
    """
    Calculate monthly PPh21 using TER (Tabel Pajak Bulanan) method.
    
    Args:
        taxable_income: Either the gross income value or a dict containing slip data
        employee: Employee document or dictionary with employee data
        company: Company name or ID
        bulan: Nomor bulan (1-12), optional if provided in taxable_income
        
    Returns:
        Dictionary with calculation results including pph21 amount
        
    Raises:
        frappe.ValidationError: For validation errors in input data
    """
    # Input validation
    if not employee:
        frappe.throw("Employee data is required for PPh21 calculation", title="Missing Employee")
        
    if not company:
        frappe.throw("Company is required for PPh21 calculation", title="Missing Company")
    
    # Handle case where taxable_income is a salary slip dictionary
    slip_data = None
    if isinstance(taxable_income, dict) and taxable_income.get("earnings") is not None:
        slip_data = taxable_income
        # Extract bulan from slip if not provided
        if not bulan and slip_data.get("start_date"):
            try:
                from frappe.utils import getdate
                bulan = getdate(slip_data.get("start_date")).month
            except Exception:
                pass

    # Ensure bulan is valid or use default
    if not bulan:
        # Try to get bulan from employee data
        if hasattr(employee, "bulan"):
            bulan = getattr(employee, "bulan")
        elif isinstance(employee, dict) and employee.get("bulan"):
            bulan = employee.get("bulan")
        else:
            # Default ke bulan berjalan jika tidak diberikan
            from datetime import datetime
            bulan = datetime.now().month
    
    # Employment type check - only process Full-time employees
    emp_type = employee.get("employment_type") if isinstance(employee, dict) else getattr(employee, "employment_type", None)
    if emp_type != "Full-time":
        return {"employment_type_checked": False, "pph21": 0.0}
    
    # Calculate bruto income
    if slip_data:
        bruto = sum_bruto_earnings(slip_data)
    else:
        # Use provided taxable_income as gross value
        bruto = flt(taxable_income)
    
    # Calculate biaya jabatan (occupational deduction)
    bj_rate = get_biaya_jabatan_rate()
    bj_cap = get_biaya_jabatan_cap_monthly()
    
    if slip_data:
        biaya_jabatan = get_biaya_jabatan_from_component(slip_data) or min(
            bruto * bj_rate / 100, bj_cap
        )
        # Calculate other deductions from slip
        pengurang_netto = sum_pengurang_netto(slip_data)
    else:
        # Standard calculations if no slip data
        biaya_jabatan = min(bruto * bj_rate / 100, bj_cap)
        pengurang_netto = 0.0  # No deductions available without slip data
    
    # Calculate netto income
    netto = bruto - biaya_jabatan - pengurang_netto
    
    # Get PTKP (non-taxable income threshold)
    try:
        ptkp = flt(get_ptkp_amount(employee) / 12)
    except ValidationError as e:
        frappe.logger().warning(str(e))
        ptkp = 0.0
    
    # Calculate PKP (taxable income after PTKP)
    pkp = max(netto - ptkp, 0)
    
    # Get TER rate based on employee code and bruto
    ter_code = get_ter_code(employee)
    try:
        rate = get_ter_rate(ter_code, bruto)
    except ValidationError as e:
        frappe.logger().warning(str(e))
        rate = 0.0
    
    # Calculate tax amount
    pph21 = round_half_up(bruto * rate / 100)
    
    # Prepare result
    result = {
        "ptkp": ptkp,
        "bruto": bruto,
        "pengurang_netto": pengurang_netto,
        "biaya_jabatan": biaya_jabatan,
        "netto": netto,
        "pkp": pkp,
        "rate": rate,
        "pph21": pph21,
        "employment_type_checked": True,
    }
    
    return result

def sum_bruto_earnings(salary_slip: Dict[str, Any]) -> float:
    """
    Sum all earning components contributing to bruto pay (including taxable natura).
    Criteria:
      - is_tax_applicable = 1
      - OR is_income_tax_component = 1
      - OR variable_based_on_taxable_salary = 1
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
            and row.get("statistical_component", 0) == 0
            and row.get("exempted_from_income_tax", 0) == 0
        ):
            total += flt(row.get("amount", 0))
    return total

def sum_pengurang_netto(slip: Dict[str, Any]) -> float:
    """
    Total pengurang netto:
      • baris deduction ber-flag is_pengurang_netto = 1  ──► fleksibel
      • ATAU nama komponen ada di PENGURANG_NETTO_NAMES
    Abaikan baris 'Biaya Jabatan'.
    """
    total = 0.0
    for row in slip.get("deductions", []):
        if "biaya jabatan" in (row.get("salary_component") or "").lower():
            continue
        if (
            row.get("is_pengurang_netto", 0) == 1
            or (row.get("salary_component") or "").lower() in PENGURANG_NETTO_NAMES
        ):
            total += flt(row.get("amount", 0))
    return total

def get_biaya_jabatan_from_component(salary_slip: Dict[str, Any]) -> float:
    """
    Get 'Biaya Jabatan' deduction from salary slip, return 0 if not present.
    """
    deductions = salary_slip.get("deductions", [])
    for row in deductions:
        if "biaya jabatan" in row.get("salary_component", "").lower():
            return flt(row.get("amount", 0))
    return 0.0