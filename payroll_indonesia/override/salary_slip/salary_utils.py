# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Utility functions for salary calculations in Indonesian payroll.
"""

import logging
from datetime import datetime, date
from typing import Any, Dict, Optional, Union, cast

import frappe
from frappe.utils import getdate, flt

from payroll_indonesia.override.salary_slip.tax_calculator import get_ytd_totals
from payroll_indonesia.constants import MONTHS_PER_YEAR

__all__ = ["calculate_ytd_and_ytm"]

logger = logging.getLogger("salary_utils")


def calculate_ytd_and_ytm(slip: Any, ref_date: Optional[Union[str, date]] = None) -> Dict[str, Any]:
    """
    Calculate year-to-date and year-to-make values for salary components.

    Args:
        slip: Salary slip document
        ref_date: Reference date for calculations (defaults to slip.posting_date)

    Returns:
        Dict with YTD and YTM values
    """
    # Use provided date or slip posting date or today
    if ref_date is None:
        ref_date = getattr(slip, "posting_date", None)
        if not ref_date:
            logger.warning(
                f"No posting_date for slip {getattr(slip, 'name', 'unknown')}, using today"
            )
            ref_date = date.today()

    # Convert to date object if string
    date_obj = getdate(ref_date)

    # Get fiscal year (from slip or derive from date)
    fiscal_year = getattr(slip, "fiscal_year", None)
    if not fiscal_year:
        fiscal_year = date_obj.year
        logger.debug(f"Derived fiscal year {fiscal_year} from date {date_obj}")

    # Calculate months remaining in the year
    months_remaining = _months_remaining(date_obj)

    # Get YTD totals
    ytd_data = get_ytd_totals(slip)

    # Extract values with defaults
    ytd_gross = flt(ytd_data.get("gross", 0))
    ytd_bpjs = flt(ytd_data.get("bpjs", 0))
    ytd_pph21 = flt(ytd_data.get("pph21", 0))

    # Current month values (not included in YTD)
    current_gross = flt(getattr(slip, "gross_pay", 0))
    current_bpjs = flt(getattr(slip, "total_bpjs", 0))
    current_pph21 = flt(getattr(slip, "pph21", 0))

    # Calculate annual targets (YTD + current + projected)
    if months_remaining > 0:
        monthly_gross = current_gross
        monthly_bpjs = current_bpjs
        monthly_pph21 = current_pph21

        projected_gross = monthly_gross * months_remaining
        projected_bpjs = monthly_bpjs * months_remaining
        projected_pph21 = monthly_pph21 * months_remaining
    else:
        # December or special case
        projected_gross = 0
        projected_bpjs = 0
        projected_pph21 = 0

    # Calculate year to make values
    ytm_gross = projected_gross
    ytm_bpjs = projected_bpjs
    ytm_pph21 = projected_pph21

    # Calculate annual totals
    annual_gross = ytd_gross + current_gross + ytm_gross
    annual_bpjs = ytd_bpjs + current_bpjs + ytm_bpjs
    annual_pph21 = ytd_pph21 + current_pph21 + ytm_pph21

    # Prepare result
    result = {
        "ytd": {
            "ytd_gross": ytd_gross,
            "ytd_bpjs": ytd_bpjs,
            "ytd_pph21": ytd_pph21,
        },
        "current": {
            "gross": current_gross,
            "bpjs": current_bpjs,
            "pph21": current_pph21,
        },
        "ytm": {
            "ytm_gross": ytm_gross,
            "ytm_bpjs": ytm_bpjs,
            "ytm_pph21": ytm_pph21,
            "months_remaining": months_remaining,
        },
        "annual": {
            "annual_gross": annual_gross,
            "annual_bpjs": annual_bpjs,
            "annual_pph21": annual_pph21,
        },
        "fiscal_year": fiscal_year,
    }

    logger.debug(f"YTD/YTM calculation for {getattr(slip, 'employee', 'unknown')}: {result}")
    return result


def _months_remaining(date_obj: date) -> int:
    """
    Calculate the number of months remaining in the year after the given date.

    Args:
        date_obj: The reference date

    Returns:
        Number of months remaining in the year (0-11)
    """
    # Convert to date object if needed
    if not isinstance(date_obj, date):
        date_obj = getdate(date_obj)

    # Calculate months remaining
    months_passed = date_obj.month
    months_remaining = MONTHS_PER_YEAR - months_passed

    return months_remaining
