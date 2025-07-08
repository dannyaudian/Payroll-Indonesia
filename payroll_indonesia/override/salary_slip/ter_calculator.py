# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:31:10 by dannyaudian

"""
TER calculator module - kalkulator TER.
"""

import logging
from typing import Any, Dict, Tuple

# from typing import Any, Dict, Tuple, TYPE_CHECKING
from functools import lru_cache

from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR,
    TER_MONTHS,
    TER_CATEGORY_A,
    TER_CATEGORY_B,
    TER_CATEGORY_C,
)

# if TYPE_CHECKING:
#     from frappe.model.document import Document

logger = logging.getLogger("ter_calc")


@lru_cache(maxsize=128)
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
    logger.warning(f"Unknown PTKP code '{ptkp_code}', defaulting to TER C")
    return TER_CATEGORY_C


@lru_cache(maxsize=128)
def get_ter_rate(ptkp_code: str, taxable_income: float) -> float:
    """
    Get TER rate based on PTKP code and income.

    Args:
        ptkp_code: Tax status code (TK0, K1, etc.)
        taxable_income: Monthly taxable income

    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    ter_category = get_ter_category(ptkp_code)
    cfg = get_live_config()

    # Get rates from config
    ter_rates = cfg.get("ter_rates", {}).get(ter_category, [])

    # If rates exist in configuration, find the appropriate one
    if ter_rates:
        # Sort rates by income_from (descending)
        sorted_rates = sorted(ter_rates, key=lambda x: float(x.get("income_from", 0)), reverse=True)

        # Find matching rate
        for rate_data in sorted_rates:
            income_from = float(rate_data.get("income_from", 0))
            income_to = float(rate_data.get("income_to", 0))
            is_highest = rate_data.get("is_highest_bracket", False)

            if taxable_income >= income_from and (
                is_highest or income_to == 0 or taxable_income < income_to
            ):
                rate = float(rate_data.get("rate", 0)) / 100.0
                logger.debug(
                    f"Found TER rate {rate * 100}% for category {ter_category}, "
                    f"income {taxable_income}"
                )
                return rate

    # Default rates if not in configuration
    default_rates = {
        TER_CATEGORY_A: 0.05,  # 5%
        TER_CATEGORY_B: 0.10,  # 10%
        TER_CATEGORY_C: 0.15,  # 15%
    }

    rate = default_rates.get(ter_category, 0.15)
    logger.warning(
        f"No matching TER rate found in config for category {ter_category}, "
        f"income {taxable_income}. Using default: {rate * 100}%"
    )
    return rate


def _get_tax_status(slip: Any) -> str:
    """Extract tax status from employee document."""
    employee = getattr(slip, "employee_doc", None)
    tax_status = "TK0"  # Default

    if employee and hasattr(employee, "status_pajak") and employee.status_pajak:
        tax_status = employee.status_pajak

    return tax_status


def _get_gross_pay(slip: Any) -> Tuple[float, bool]:
    """
    Extract gross pay from salary slip and detect if adjustment is needed.

    Returns:
        Tuple of (gross_pay, needs_adjustment)
    """
    gross_pay = float(getattr(slip, "gross_pay", 0))
    needs_adjustment = False

    # Check if bypass flag is set
    if hasattr(slip, "bypass_annual_detection") and slip.bypass_annual_detection:
        return gross_pay, needs_adjustment

    # Get total earnings
    total_earnings = 0
    if hasattr(slip, "earnings") and slip.earnings:
        total_earnings = sum(float(getattr(e, "amount", 0)) for e in slip.earnings)

    # Get basic salary
    basic_salary = 0
    if hasattr(slip, "earnings") and slip.earnings:
        for e in slip.earnings:
            if getattr(e, "salary_component", "") in ["Gaji Pokok", "Basic Salary", "Basic Pay"]:
                basic_salary = float(getattr(e, "amount", 0))
                break

    # Check conditions for annual value
    if total_earnings > 0 and gross_pay > total_earnings * 3:
        needs_adjustment = True
    elif basic_salary > 0 and gross_pay > basic_salary * 10:
        needs_adjustment = True

    return gross_pay, needs_adjustment


def _adjust_annual_to_monthly(annual_value: float) -> float:
    """Convert annual value to monthly."""
    return annual_value / MONTHS_PER_YEAR


def _update_slip_fields(slip: Any, values: Dict[str, Any]) -> None:
    """Update salary slip fields with calculated values."""
    for field, value in values.items():
        if hasattr(slip, field):
            setattr(slip, field, value)


def calculate_monthly_pph_with_ter(slip: Any) -> Dict[str, Any]:
    """
    Calculate PPh 21 using TER method as per PMK 168/2023.

    Args:
        slip: Salary slip document

    Returns:
        dict: Calculation results
    """
    # Get tax status
    tax_status = _get_tax_status(slip)

    # Get gross pay and detect if adjustment needed
    gross_pay, needs_adjustment = _get_gross_pay(slip)

    # Adjust if needed (likely annual value)
    if needs_adjustment:
        original_gross = gross_pay
        gross_pay = _adjust_annual_to_monthly(gross_pay)
        logger.info(
            f"Adjusted gross pay from {original_gross} to {gross_pay} "
            f"for employee {getattr(slip, 'employee', 'unknown')}"
        )

    # Calculate annual taxable income based on TER months
    annual_taxable_income = gross_pay * TER_MONTHS

    # Get TER rate based on tax status and income
    ter_rate = get_ter_rate(tax_status, gross_pay)

    # Calculate monthly tax
    monthly_tax = gross_pay * ter_rate

    # Store values in salary slip
    _update_slip_fields(
        slip,
        {
            "monthly_gross_for_ter": gross_pay,
            "annual_taxable_income": annual_taxable_income,
            "ter_category": get_ter_category(tax_status),
            "ter_rate": ter_rate * 100,  # Store as percentage
            "is_using_ter": 1,
            "pph21": monthly_tax,  # Set calculated tax
        },
    )

    # Prepare result for reporting
    result = {
        "tax_method": "TER",
        "tax_status": tax_status,
        "ter_category": get_ter_category(tax_status),
        "gross_pay": gross_pay,
        "annual_taxable_income": annual_taxable_income,
        "ter_rate": ter_rate,
        "monthly_tax": monthly_tax,
        "adjusted_from_annual": needs_adjustment,
    }

    employee_id = getattr(slip, "employee", "unknown")
    logger.debug(f"TER calculation for {employee_id}: {result}")
    return result
