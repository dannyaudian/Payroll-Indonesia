# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 01:06:03 by dannyaudian

"""
BPJS calculator module - satu-satunya kalkulator BPJS.
Single source of BPJS calculation logic.
"""

import logging
from typing import Any, Dict

from payroll_indonesia.config import get_live_config

logger = logging.getLogger("bpjs_calc")

# Default BPJS values - used when config is not available
DEFAULT_BPJS_VALUES = {
    "default_umr": 4900000,
    "kesehatan_employee_percent": 1.0,
    "kesehatan_employer_percent": 4.0,
    "kesehatan_max_salary": 12000000,
    "jht_employee_percent": 2.0,
    "jht_employer_percent": 3.7,
    "jp_employee_percent": 1.0,
    "jp_employer_percent": 2.0,
    "jp_max_salary": 9077600,
    "jkk_percent": 0.24,
    "jkm_percent": 0.3,
}


def _get_bpjs_config() -> Dict[str, Any]:
    """Get BPJS configuration with fallback to defaults."""
    try:
        cfg = get_live_config()
        return cfg.get("bpjs", DEFAULT_BPJS_VALUES)
    except Exception as e:
        logger.warning(f"Could not load live config: {e}. Using defaults.")
        return DEFAULT_BPJS_VALUES


def _validate_percentage(value: Any, name: str) -> bool:
    """Validate a percentage value is between 0-100."""
    try:
        val = float(value)
        if val < 0 or val > 100:
            logger.error(f"BPJS config {name} out of bounds: {val}")
            return False
        return True
    except Exception:
        logger.error(f"BPJS config {name} not float: {value}")
        return False


def _validate_bpjs_config(bpjs_config: Dict[str, Any]) -> bool:
    """Validate all BPJS percentage values."""
    percentage_fields = [
        "kesehatan_employee_percent",
        "kesehatan_employer_percent",
        "jht_employee_percent",
        "jht_employer_percent",
        "jp_employee_percent",
        "jp_employer_percent",
        "jkk_percent",
        "jkm_percent",
    ]

    for field in percentage_fields:
        if not _validate_percentage(bpjs_config.get(field, 0), field):
            return False
    return True


def _get_base_salary(slip: Any, default_umr: float) -> float:
    """Extract base salary from salary slip."""
    base_salary = 0.0

    # Try gross_pay first
    if hasattr(slip, "gross_pay") and slip.gross_pay:
        base_salary = float(slip.gross_pay)
    # Try earnings if no gross_pay
    elif hasattr(slip, "earnings"):
        for earning in getattr(slip, "earnings", []):
            if getattr(earning, "salary_component", "") == "Gaji Pokok":
                base_salary += float(getattr(earning, "amount", 0))

    # Use default UMR if no base salary found
    if not base_salary:
        base_salary = default_umr
        logger.info(f"No base salary found. Using default UMR: {base_salary}")

    return base_salary


def _calculate_employee_contributions(base_salary: float, kesehatan_salary: float,
                                      jp_salary: float, bpjs_config: Dict[str, Any]) -> Dict[str, float]:
    """Calculate employee BPJS contributions."""
    kesehatan_emp_pct = bpjs_config.get("kesehatan_employee_percent", 1.0)
    jht_emp_pct = bpjs_config.get("jht_employee_percent", 2.0)
    jp_emp_pct = bpjs_config.get("jp_employee_percent", 1.0)

    return {
        "kesehatan_employee": kesehatan_salary * (kesehatan_emp_pct / 100.0),
        "jht_employee": base_salary * (jht_emp_pct / 100.0),
        "jp_employee": jp_salary * (jp_emp_pct / 100.0),
    }


def _calculate_employer_contributions(base_salary: float, kesehatan_salary: float,
                                      jp_salary: float, bpjs_config: Dict[str, Any]) -> Dict[str, float]:
    """Calculate employer BPJS contributions."""
    kesehatan_emp_pct = bpjs_config.get("kesehatan_employer_percent", 4.0)
    jht_emp_pct = bpjs_config.get("jht_employer_percent", 3.7)
    jp_emp_pct = bpjs_config.get("jp_employer_percent", 2.0)
    jkk_pct = bpjs_config.get("jkk_percent", 0.24)
    jkm_pct = bpjs_config.get("jkm_percent", 0.3)

    return {
        "kesehatan_employer": kesehatan_salary * (kesehatan_emp_pct / 100.0),
        "jht_employer": base_salary * (jht_emp_pct / 100.0),
        "jp_employer": jp_salary * (jp_emp_pct / 100.0),
        "jkk": base_salary * (jkk_pct / 100.0),
        "jkm": base_salary * (jkm_pct / 100.0),
    }


def calculate_components(slip: Any) -> Dict[str, float]:
    """
    Calculate BPJS (employee & employer) for salary slip.
    Returns dictionary with all components and totals.
    """
    # Get BPJS configuration
    bpjs_config = _get_bpjs_config()

    # Validate configuration
    if not _validate_bpjs_config(bpjs_config):
        logger.error("BPJS config percentages invalid. Calculation aborted.")
        return {}

    # Get salary caps
    kesehatan_max = float(bpjs_config.get("kesehatan_max_salary", 12000000))
    jp_max = float(bpjs_config.get("jp_max_salary", 9077600))
    default_umr = float(bpjs_config.get("default_umr", 4900000))

    # Determine base salary
    base_salary = _get_base_salary(slip, default_umr)

    # Apply salary caps
    kesehatan_salary = min(base_salary, kesehatan_max)
    jp_salary = min(base_salary, jp_max)

    # Calculate employee contributions
    employee_contributions = _calculate_employee_contributions(
        base_salary, kesehatan_salary, jp_salary, bpjs_config
    )

    # Calculate employer contributions
    employer_contributions = _calculate_employer_contributions(
        base_salary, kesehatan_salary, jp_salary, bpjs_config
    )

    # Calculate totals
    total_employee = sum(employee_contributions.values())
    total_employer = sum(employer_contributions.values())

    # Combine results and round values
    result = {
        **{k: round(v) for k, v in employee_contributions.items()},
        **{k: round(v) for k, v in employer_contributions.items()},
        "total_employee": round(total_employee),
        "total_employer": round(total_employer),
    }

    # Log calculation details
    employee_name = getattr(slip, 'employee', 'Unknown')
    logger.debug(f"BPJS calculation for {employee_name}: {result}")

    return result
