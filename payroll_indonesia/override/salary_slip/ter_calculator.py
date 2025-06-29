# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:05:31 by dannyaudian

"""
TER calculator module - PPh 21 with Tarif Efektif Rata-rata.
"""

import logging
from typing import Any, Dict, Optional, Union, cast, TYPE_CHECKING

from payroll_indonesia.config import get_live_config
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR,
    TER_CATEGORY_A,
    TER_CATEGORY_B,
    TER_CATEGORY_C,
)

if TYPE_CHECKING:
    from frappe.model.document import Document

logger = logging.getLogger("ter_calc")


def get_ter_category(ptkp_code: str) -> str:
    """
    Map PTKP status to TER category based on PMK 168/2023.
    
    Args:
        ptkp_code: Tax status code (TK0, K1, etc.)
        
    Returns:
        str: TER category (TER A, TER B, or TER C)
    """
    cfg = get_live_config()
    ptkp_to_ter = cfg.get("ptkp_to_ter_mapping", {})
    
    # Use configuration mapping if available
    if ptkp_code in ptkp_to_ter:
        return ptkp_to_ter[ptkp_code]
    
    # Default mapping logic
    prefix = ptkp_code[:2] if len(ptkp_code) >= 2 else ptkp_code
    suffix = ptkp_code[2:] if len(ptkp_code) >= 3 else "0"
    
    if ptkp_code == "TK0":
        return TER_CATEGORY_A
    elif prefix == "TK" and suffix in ["1", "2", "3"]:
        return TER_CATEGORY_B
    elif prefix == "K" and suffix == "0":
        return TER_CATEGORY_B
    elif prefix == "K" and suffix in ["1", "2", "3"]:
        return TER_CATEGORY_C
    elif prefix == "HB":  # Single parent
        return TER_CATEGORY_C
    
    # Default to highest category
    return TER_CATEGORY_C


def get_ter_rate(ter_category: str, taxable_income: float) -> float:
    """
    Get TER rate based on category and income.
    
    Args:
        ter_category: TER category (TER A, TER B, or TER C)
        taxable_income: Monthly taxable income
        
    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    cfg = get_live_config()
    ter_rates = cfg.get("ter_rates", {}).get(ter_category, [])
    
    # If rates exist in configuration, find the appropriate one
    if ter_rates:
        # Sort rates by income_from (descending)
        sorted_rates = sorted(
            ter_rates, 
            key=lambda x: float(x.get("income_from", 0)), 
            reverse=True
        )
        
        # Find matching rate
        for rate_data in sorted_rates:
            income_from = float(rate_data.get("income_from", 0))
            income_to = float(rate_data.get("income_to", 0))
            is_highest = rate_data.get("is_highest_bracket", False)
            
            if taxable_income >= income_from and (
                is_highest or income_to == 0 or taxable_income < income_to
            ):
                return float(rate_data.get("rate", 0)) / 100.0
    
    # Default rates if not in configuration
    default_rates = {
        TER_CATEGORY_A: 0.05,  # 5%
        TER_CATEGORY_B: 0.10,  # 10%
        TER_CATEGORY_C: 0.15   # 15%
    }
    
    return default_rates.get(ter_category, 0.15)


def calculate_monthly_pph_with_ter(slip: Any) -> Dict[str, Any]:
    """
    Calculate PPh 21 using TER method as per PMK 168/2023.
    
    Args:
        slip: Salary slip document
        
    Returns:
        dict: Calculation results
    """
    # Get tax status and ensure it exists
    employee = getattr(slip, "employee_doc", None)
    tax_status = "TK0"  # Default
    if employee and hasattr(employee, "status_pajak") and employee.status_pajak:
        tax_status = employee.status_pajak
    
    # Get gross pay
    gross_pay = float(getattr(slip, "gross_pay", 0))
    
    # Detect annual values and adjust if needed
    if should_adjust_annual_value(slip, gross_pay):
        gross_pay = adjust_annual_to_monthly(gross_pay)
        logger.info(f"Adjusted annual value to monthly: {gross_pay}")
    
    # Calculate annual taxable income
    annual_taxable_income = gross_pay * MONTHS_PER_YEAR
    
    # Determine TER category
    ter_category = get_ter_category(tax_status)
    
    # Get TER rate
    ter_rate = get_ter_rate(ter_category, gross_pay)
    
    # Calculate monthly tax
    monthly_tax = gross_pay * ter_rate
    
    # Store values in salary slip
    if hasattr(slip, "monthly_gross_for_ter"):
        slip.monthly_gross_for_ter = gross_pay
    if hasattr(slip, "annual_taxable_income"):
        slip.annual_taxable_income = annual_taxable_income
    if hasattr(slip, "ter_category"):
        slip.ter_category = ter_category
    if hasattr(slip, "ter_rate"):
        slip.ter_rate = ter_rate * 100  # Store as percentage
    if hasattr(slip, "is_using_ter"):
        slip.is_using_ter = 1
    
    # Prepare result for reporting
    result = {
        "tax_method": "TER",
        "tax_status": tax_status,
        "ter_category": ter_category,
        "gross_pay": gross_pay,
        "annual_taxable_income": annual_taxable_income,
        "ter_rate": ter_rate,
        "monthly_tax": monthly_tax
    }
    
    logger.debug(f"TER calculation for {getattr(slip, 'employee', '')}: {result}")
    return result


def should_adjust_annual_value(slip: Any, gross_pay: float) -> bool:
    """
    Detect if gross_pay is likely an annual value that needs adjustment.
    
    Args:
        slip: Salary slip document
        gross_pay: Gross pay amount
        
    Returns:
        bool: True if value is likely annual
    """
    # Check if bypass flag is set
    if hasattr(slip, "bypass_annual_detection") and slip.bypass_annual_detection:
        return False
    
    # Get total earnings
    total_earnings = 0
    if hasattr(slip, "earnings") and slip.earnings:
        total_earnings = sum(float(getattr(e, "amount", 0)) for e in slip.earnings)
    
    # Get basic salary
    basic_salary = 0
    if hasattr(slip, "earnings") and slip.earnings:
        for e in slip.earnings:
            if getattr(e, "salary_component", "") in [
                "Gaji Pokok", "Basic Salary", "Basic Pay"
            ]:
                basic_salary = float(getattr(e, "amount", 0))
                break
    
    # Check conditions
    if total_earnings > 0 and gross_pay > total_earnings * 3:
        return True
    
    if basic_salary > 0 and gross_pay > basic_salary * 10:
        return True
    
    return False


def adjust_annual_to_monthly(annual_value: float) -> float:
    """
    Convert annual value to monthly.
    
    Args:
        annual_value: Annual value
        
    Returns:
        float: Monthly value
    """
    return annual_value / MONTHS_PER_YEAR
