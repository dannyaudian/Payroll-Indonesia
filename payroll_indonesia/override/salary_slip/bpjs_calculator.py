# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:29:18 by dannyaudian

"""
BPJS calculator module - satu-satunya kalkulator BPJS.
"""

import logging
from typing import Any, Dict

# from typing import Any, Dict, Optional, TYPE_CHECKING

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

# if TYPE_CHECKING:
#     from frappe.model.document import Document

logger = logging.getLogger("bpjs_calc")


def _validate_percentage(key: str, value: Any) -> bool:
    """Validate that a given value is a valid percentage (0-100)."""
    try:
        percentage = float(value)
        if 0 <= percentage <= 100:
            return True
        logger.error(f"BPJS config {key} out of bounds: {percentage}")
    except (ValueError, TypeError):
        logger.error(f"BPJS config {key} not float: {value}")
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
        logger.error("BPJS config percentages invalid. Calculation aborted.")
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

    # Apply salary caps
    kesehatan_salary = min(base_salary, kesehatan_max)
    jp_salary = min(base_salary, jp_max)

    # Calculate employee portions
    kesehatan_employee = kesehatan_salary * (percentages["kesehatan_emp"] / 100)
    jht_employee = base_salary * (percentages["jht_emp"] / 100)
    jp_employee = jp_salary * (percentages["jp_emp"] / 100)

    # Calculate employer portions
    kesehatan_employer = kesehatan_salary * (percentages["kesehatan_com"] / 100)
    jht_employer = base_salary * (percentages["jht_com"] / 100)
    jp_employer = jp_salary * (percentages["jp_com"] / 100)
    jkk_amount = base_salary * (percentages["jkk"] / 100)
    jkm_amount = base_salary * (percentages["jkm"] / 100)

    # Calculate totals
    total_employee = kesehatan_employee + jht_employee + jp_employee
    total_employer = kesehatan_employer + jht_employer + jp_employer + jkk_amount + jkm_amount

    # Prepare result dictionary
    result = {
        "kesehatan_employee": round(kesehatan_employee),
        "kesehatan_employer": round(kesehatan_employer),
        "jht_employee": round(jht_employee),
        "jht_employer": round(jht_employer),
        "jp_employee": round(jp_employee),
        "jp_employer": round(jp_employer),
        "jkk": round(jkk_amount),
        "jkm": round(jkm_amount),
        "total_employee": round(total_employee),
        "total_employer": round(total_employer),
    }

    employee_id = getattr(slip, "employee", "unknown")
    logger.debug(f"BPJS calculation for {employee_id}: {result}")
    return result
