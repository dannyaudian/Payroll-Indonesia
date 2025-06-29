# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 01:06:03 by dannyaudian

"""
BPJS calculator module - single source of BPJS calculation logic.
"""

import logging
from typing import Any, Dict, TYPE_CHECKING

from payroll_indonesia.config import get_live_config
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

if TYPE_CHECKING:
    from frappe.model.document import Document

logger = logging.getLogger("bpjs_calc")


def validate_bpjs_percentages(cfg: Dict[str, Any]) -> bool:
    """
    Validate percentage values in BPJS config.
    Returns True if all in 0..100, False otherwise.
    """
    bpjs = cfg.get("bpjs", {})
    keys = [
        "kesehatan_employee_percent",
        "kesehatan_employer_percent",
        "jht_employee_percent",
        "jht_employer_percent",
        "jp_employee_percent",
        "jp_employer_percent",
        "jkk_percent",
        "jkm_percent",
    ]
    for key in keys:
        val = bpjs.get(key, 0)
        try:
            v = float(val)
            if v < 0 or v > 100:
                logger.error(f"BPJS config {key} out of bounds: {v}")
                return False
        except Exception:
            logger.error(f"BPJS config {key} not float: {val}")
            return False
    return True


def calculate_components(slip: Any) -> Dict[str, float]:
    """
    Calculate BPJS (employee & employer) for salary slip.
    Returns dictionary with all components and totals.
    """
    cfg = get_live_config()
    if not validate_bpjs_percentages(cfg):
        logger.error("BPJS config percentages invalid. Calculation aborted.")
        return {}

    bpjs = cfg.get("bpjs", {})

    # Salary caps (maximum salary considered)
    kesehatan_max = float(bpjs.get(
        "kesehatan_max_salary", 
        BPJS_KESEHATAN_MAX_SALARY
    ))
    jp_max = float(bpjs.get(
        "jp_max_salary", 
        BPJS_JP_MAX_SALARY
    ))

    # Percentages
    kesehatan_emp = float(bpjs.get(
        "kesehatan_employee_percent", 
        BPJS_KESEHATAN_EMPLOYEE_PERCENT
    ))
    kesehatan_com = float(bpjs.get(
        "kesehatan_employer_percent", 
        BPJS_KESEHATAN_EMPLOYER_PERCENT
    ))
    jht_emp = float(bpjs.get(
        "jht_employee_percent", 
        BPJS_JHT_EMPLOYEE_PERCENT
    ))
    jht_com = float(bpjs.get(
        "jht_employer_percent", 
        BPJS_JHT_EMPLOYER_PERCENT
    ))
    jp_emp = float(bpjs.get(
        "jp_employee_percent", 
        BPJS_JP_EMPLOYEE_PERCENT
    ))
    jp_com = float(bpjs.get(
        "jp_employer_percent", 
        BPJS_JP_EMPLOYER_PERCENT
    ))
    jkk = float(bpjs.get(
        "jkk_percent", 
        BPJS_JKK_PERCENT
    ))
    jkm = float(bpjs.get(
        "jkm_percent", 
        BPJS_JKM_PERCENT
    ))

    # Determine base salary for BPJS
    base_salary = 0.0
    if hasattr(slip, "gross_pay") and slip.gross_pay:
        base_salary = float(slip.gross_pay)
    elif hasattr(slip, "earnings"):
        for e in getattr(slip, "earnings", []):
            if getattr(e, "salary_component", "") == "Gaji Pokok":
                base_salary += float(getattr(e, "amount", 0))
    if not base_salary:
        base_salary = float(bpjs.get("default_umr", DEFAULT_UMR))
        logger.info(f"No base salary found. Using default UMR: {base_salary}")

    # Apply salary caps
    kesehatan_salary = min(base_salary, kesehatan_max)
    jp_salary = min(base_salary, jp_max)

    # Employee portion
    kesehatan_employee = kesehatan_salary * (kesehatan_emp / 100.0)
    jht_employee = base_salary * (jht_emp / 100.0)
    jp_employee = jp_salary * (jp_emp / 100.0)

    # Employer portion
    kesehatan_employer = kesehatan_salary * (kesehatan_com / 100.0)
    jht_employer = base_salary * (jht_com / 100.0)
    jp_employer = jp_salary * (jp_com / 100.0)
    jkk_amount = base_salary * (jkk / 100.0)
    jkm_amount = base_salary * (jkm / 100.0)

    # Totals
    total_employee = (
        kesehatan_employee + jht_employee + jp_employee
    )
    total_employer = (
        kesehatan_employer + jht_employer +
        jp_employer + jkk_amount + jkm_amount
    )

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
    logger.debug(f"BPJS calculation for {getattr(slip, 'employee', '')}: {result}")
    return result
