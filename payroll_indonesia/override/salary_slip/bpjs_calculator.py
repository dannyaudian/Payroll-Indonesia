# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:29:18 by dannyaudian

"""
BPJS calculator module - satu-satunya kalkulator BPJS.

Provides standardized calculation functions for BPJS deductions in Indonesian payroll.
"""

from typing import Any, Dict, Optional, Union

import frappe
from frappe.utils import flt

from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.constants import (
    DEFAULT_UMR,
    BPJS_KESEHATAN_EMPLOYEE_PERCENT,
    BPJS_KESEHATAN_EMPLOYER_PERCENT,
    BPJS_KESEHATAN_MAX_SALARY,
    BPJS_JHT_EMPLOYEE_PERCENT,
    BPJS_JHT_EMPLOYER_PERCENT,
    BPJS_JP_EMPLOYEE_PERCENT,
    BPJS_JP_EMPLOYER_PERCENT,
    BPJS_JP_MAX_SALARY,
    BPJS_JKK_PERCENT,
    BPJS_JKM_PERCENT,
)

# Define public API
__all__ = ["calculate_bpjs", "calculate_components", "validate_bpjs_percentages"]


def is_valid_percent(value: Union[float, int, str]) -> bool:
    """Check if a value is a valid percentage between 0 and 100."""
    try:
        percent = flt(value)
        return 0 <= percent <= 100
    except (ValueError, TypeError):
        return False


def calculate_bpjs(
    base_salary: float,
    rate_percent: float,
    *,
    max_salary: Optional[float] = None,
) -> int:
    """
    Calculate BPJS deduction amount based on salary and rate.
    
    Args:
        base_salary: The base salary amount for calculation
        rate_percent: The BPJS rate percentage (e.g., 1.0 for 1%)
        max_salary: Optional maximum salary cap for the calculation
        
    Returns:
        int: The calculated BPJS amount as a rounded integer (IDR has no cents)
    """
    # Ensure inputs are proper float values
    base_salary = flt(base_salary)
    rate_percent = flt(rate_percent)
    
    # Validate inputs
    if base_salary < 0:
        logger.warning(f"Negative base salary provided: {base_salary}. Using absolute value.")
        base_salary = abs(base_salary)
        
    if not is_valid_percent(rate_percent):
        logger.warning(
            f"Invalid BPJS rate percentage: {rate_percent}. "
            f"Should be between 0-100. Using absolute value capped at 100."
        )
        rate_percent = min(abs(rate_percent), 100)
    
    # Apply maximum salary cap if provided
    if max_salary is not None and max_salary > 0 and base_salary > max_salary:
        base_salary = max_salary
    
    # Calculate the BPJS amount (rate_percent is a percentage, so divide by 100)
    bpjs_amount = base_salary * (rate_percent / 100.0)
    
    # Round to nearest whole number (IDR doesn't have cents)
    return round(bpjs_amount)


def _validate_percentage(key: str, value: Any) -> bool:
    """Validate that a given value is a valid percentage (0-100)."""
    try:
        percentage = float(value)
        if 0 <= percentage <= 100:
            return True
        logger.warning(f"BPJS config {key} out of bounds: {percentage}")
    except (ValueError, TypeError):
        logger.warning(f"BPJS config {key} not float: {value}")
    return False


def validate_bpjs_percentages(cfg: Dict[str, Any]) -> bool:
    """
    Validate all percentage values in BPJS config.
    Returns True if all are within 0-100 range, False otherwise.
    """
    bpjs = cfg.get("bpjs", {})
    percentage_keys = [
        "kesehatan_employee_percent",
        "kesehatan_employer_percent",
        "jht_employee_percent",
        "jht_employer_percent",
        "jp_employee_percent",
        "jp_employer_percent",
        "jkk_percent",
        "jkm_percent",
    ]

    return all(_validate_percentage(key, bpjs.get(key, 0)) for key in percentage_keys)


def _get_base_salary(slip: Any) -> float:
    """Extract base salary from salary slip or return default UMR."""
    base_salary = 0.0

    # Try to get from gross_pay attribute
    if hasattr(slip, "gross_pay") and slip.gross_pay:
        base_salary = float(slip.gross_pay)
        return base_salary

    # Try to get from earnings list (looking for "Gaji Pokok")
    if hasattr(slip, "earnings"):
        for earning in getattr(slip, "earnings", []):
            if getattr(earning, "salary_component", "") == "Gaji Pokok":
                base_salary += float(getattr(earning, "amount", 0))
        if base_salary > 0:
            return base_salary

    # Use default UMR if no base salary found
    config = get_live_config()
    default_umr = float(config.get("bpjs", {}).get("default_umr", DEFAULT_UMR))
    logger.info(f"No base salary found. Using default UMR: {default_umr}")
    return default_umr


def calculate_components(slip: Any) -> Dict[str, float]:
    """
    Calculate BPJS (employee & employer) components for salary slip.
    Returns dictionary with all components and totals.
    """
    cfg = get_live_config()
    if not validate_bpjs_percentages(cfg):
        logger.warning("BPJS config percentages invalid. Calculation aborted.")
        return {}

    bpjs_config = cfg.get("bpjs", {})

    # Get base salary
    base_salary = _get_base_salary(slip)

    # Get salary caps from config or defaults
    kesehatan_max = float(bpjs_config.get("kesehatan_max_salary", BPJS_KESEHATAN_MAX_SALARY))
    jp_max = float(bpjs_config.get("jp_max_salary", BPJS_JP_MAX_SALARY))

    # Get percentages from config or defaults
    percentages = {
        "kesehatan_emp": float(
            bpjs_config.get("kesehatan_employee_percent", BPJS_KESEHATAN_EMPLOYEE_PERCENT)
        ),
        "kesehatan_com": float(
            bpjs_config.get("kesehatan_employer_percent", BPJS_KESEHATAN_EMPLOYER_PERCENT)
        ),
        "jht_emp": float(bpjs_config.get("jht_employee_percent", BPJS_JHT_EMPLOYEE_PERCENT)),
        "jht_com": float(bpjs_config.get("jht_employer_percent", BPJS_JHT_EMPLOYER_PERCENT)),
        "jp_emp": float(bpjs_config.get("jp_employee_percent", BPJS_JP_EMPLOYEE_PERCENT)),
        "jp_com": float(bpjs_config.get("jp_employer_percent", BPJS_JP_EMPLOYER_PERCENT)),
        "jkk": float(bpjs_config.get("jkk_percent", BPJS_JKK_PERCENT)),
        "jkm": float(bpjs_config.get("jkm_percent", BPJS_JKM_PERCENT)),
    }

    # Use the calculate_bpjs function for each component
    kesehatan_employee = calculate_bpjs(
        base_salary, percentages["kesehatan_emp"], max_salary=kesehatan_max
    )
    jht_employee = calculate_bpjs(base_salary, percentages["jht_emp"])
    jp_employee = calculate_bpjs(base_salary, percentages["jp_emp"], max_salary=jp_max)

    kesehatan_employer = calculate_bpjs(
        base_salary, percentages["kesehatan_com"], max_salary=kesehatan_max
    )
    jht_employer = calculate_bpjs(base_salary, percentages["jht_com"])
    jp_employer = calculate_bpjs(base_salary, percentages["jp_com"], max_salary=jp_max)
    jkk_amount = calculate_bpjs(base_salary, percentages["jkk"])
    jkm_amount = calculate_bpjs(base_salary, percentages["jkm"])

    # Calculate totals
    total_employee = kesehatan_employee + jht_employee + jp_employee
    total_employer = kesehatan_employer + jht_employer + jp_employer + jkk_amount + jkm_amount

    # Prepare result dictionary
    result = {
        "kesehatan_employee": kesehatan_employee,
        "kesehatan_employer": kesehatan_employer,
        "jht_employee": jht_employee,
        "jht_employer": jht_employer,
        "jp_employee": jp_employee,
        "jp_employer": jp_employer,
        "jkk": jkk_amount,
        "jkm": jkm_amount,
        "total_employee": total_employee,
        "total_employer": total_employer,
    }

    employee_id = getattr(slip, "employee", "unknown")
    logger.debug(f"BPJS calculation for {employee_id}: {result}")
    return result