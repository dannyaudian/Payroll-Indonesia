# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 by dannyaudian

"""
Tax calculator module - PPh 21 (progresif & tahunan)
"""

import logging
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime

import frappe

from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR,
    BIAYA_JABATAN_PERCENT,
    BIAYA_JABATAN_MAX,
)

__all__ = [
    "get_tax_brackets",
    "get_ptkp_value",
    "calculate_progressive_tax",
    "get_tax_status",
    "get_ytd_totals",
    "get_slip_year_month",
    "is_december_calculation",
    "update_slip_fields",
    "calculate_monthly_pph_progressive",
    "calculate_december_pph",
]

logger = logging.getLogger("tax_calc")


def get_tax_brackets() -> List[Dict[str, Any]]:
    """
    Get progressive tax brackets from config.
    Returns sorted list of brackets by income_from.
    """
    cfg = get_live_config()
    brackets = cfg.get("tax", {}).get("brackets", [])

    if brackets:
        return sorted(brackets, key=lambda x: float(x.get("income_from", 0)))

    # Default tax brackets (as of 2025)
    return [
        {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
        {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
        {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
        {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
        {"income_from": 5000000000, "income_to": 0, "tax_rate": 35},
    ]


def get_ptkp_value(tax_status: str) -> float:
    """
    Get annual PTKP (non-taxable income) value based on tax status.
    """
    cfg = get_live_config()
    ptkp_values = cfg.get("ptkp", {})

    if tax_status in ptkp_values:
        return float(ptkp_values[tax_status])

    # Default PTKP values (as of 2025)
    default_values = {
        "TK0": 54000000,
        "TK1": 58500000,
        "TK2": 63000000,
        "TK3": 67500000,
        "K0": 58500000,
        "K1": 63000000,
        "K2": 67500000,
        "K3": 72000000,
        "HB0": 112500000,
        "HB1": 117000000,
        "HB2": 121500000,
        "HB3": 126000000,
    }

    return float(default_values.get(tax_status, 54000000))


def calculate_progressive_tax(pkp: float) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Calculate PPh 21 using progressive method.
    Returns total tax and detailed breakdown per bracket.
    """
    if pkp <= 0:
        return 0.0, []

    brackets = get_tax_brackets()
    tax = 0.0
    details = []
    remaining = pkp

    for bracket in brackets:
        income_from = float(bracket.get("income_from", 0))
        income_to = float(bracket.get("income_to", 0))
        rate = float(bracket.get("tax_rate", 0)) / 100.0

        # Handle top bracket (no upper limit)
        if income_to == 0 or income_to > remaining + income_from:
            tax_in_bracket = remaining * rate
            tax += tax_in_bracket
            details.append(
                {
                    "from": income_from,
                    "to": income_from + remaining,
                    "amount": remaining,
                    "rate": rate * 100,
                    "tax": tax_in_bracket,
                }
            )
            break

        # Middle brackets
        taxable_in_bracket = income_to - income_from
        if remaining <= taxable_in_bracket:
            tax_in_bracket = remaining * rate
            tax += tax_in_bracket
            details.append(
                {
                    "from": income_from,
                    "to": income_from + remaining,
                    "amount": remaining,
                    "rate": rate * 100,
                    "tax": tax_in_bracket,
                }
            )
            break
        else:
            tax_in_bracket = taxable_in_bracket * rate
            tax += tax_in_bracket
            details.append(
                {
                    "from": income_from,
                    "to": income_to,
                    "amount": taxable_in_bracket,
                    "rate": rate * 100,
                    "tax": tax_in_bracket,
                }
            )
            remaining -= taxable_in_bracket

    return tax, details


def get_tax_status(slip: Any) -> str:
    """Extract tax status from employee document or return default."""
    employee = getattr(slip, "employee_doc", None)
    default_status = "TK0"

    if not employee:
        return default_status

    if hasattr(employee, "status_pajak") and employee.status_pajak:
        return employee.status_pajak

    return default_status


def get_ytd_totals(slip: Any) -> Dict[str, float]:
    """
    Get year-to-date totals for gross pay, BPJS, and PPh 21.
    Aggregates data from all salary slips in the same fiscal year up to the slip's posting date.

    Args:
        slip: The salary slip object

    Returns:
        Dictionary with YTD totals for gross, bpjs, and pph21
    """
    year, _ = get_slip_year_month(slip)
    employee = getattr(slip, "employee", None)
    posting_date = getattr(slip, "posting_date", None)

    if not employee or not posting_date:
        logger.warning("Missing employee or posting_date in slip, returning zeros")
        return {"gross": 0.0, "bpjs": 0.0, "pph21": 0.0}

    logger.info(f"Fetching YTD totals for employee {employee}, year {year}")

    # Check cache first
    cache_key = f"ytd_totals:{employee}:{year}:{posting_date}"
    cached_result = frappe.cache().get_value(cache_key)
    if cached_result:
        logger.debug(f"Using cached YTD totals for {employee}")
        return cached_result

    # Default result if no data is found
    result = {"gross": 0.0, "bpjs": 0.0, "pph21": 0.0}

    try:
        # Build fields list based on available columns
        select_fields = []
        field_mappings = {
            "gross_pay": "gross",
            "base_gross_pay": "gross",
            "total_bpjs": "bpjs",
            "bpjs_amount": "bpjs",
            "base_bpjs": "bpjs",
            "pph21": "pph21",
            "pph21_tax": "pph21",
            "base_pph21": "pph21",
        }

        for db_field, result_field in field_mappings.items():
            if frappe.db.has_column("Salary Slip", db_field):
                select_fields.append(f"SUM(`{db_field}`) as {result_field}")

        if not select_fields:
            logger.warning("No matching columns found in Salary Slip table")
            return result

        # Query for YTD totals
        filters = {
            "docstatus": 1,
            "employee": employee,
            "posting_date": ["<=", posting_date],
        }

        # Add year filter - checking fiscal year if available, otherwise calendar year
        if frappe.db.has_column("Salary Slip", "fiscal_year"):
            filters["fiscal_year"] = year
        else:
            filters["posting_date"] = ["between", [f"{year}-01-01", f"{year}-12-31"]]

        ytd_data = frappe.db.sql(
            f"""
            SELECT {', '.join(select_fields)}
            FROM `tabSalary Slip`
            WHERE docstatus = 1
              AND employee = %s
              AND posting_date <= %s
              AND YEAR(posting_date) = %s
            """,
            (employee, posting_date, year),
            as_dict=1,
        )

        if ytd_data and len(ytd_data) > 0:
            # Update result with non-null values from query
            for key in result.keys():
                if key in ytd_data[0] and ytd_data[0][key] is not None:
                    result[key] = float(ytd_data[0][key])

        # Cache the result
        frappe.cache().set_value(cache_key, result, expires_in_sec=300)

    except Exception as e:
        logger.error(f"Error calculating YTD totals for {employee}: {str(e)}")

    return result


def get_slip_year_month(slip: Any) -> Tuple[int, int]:
    """Extract year and month from salary slip start date."""
    if hasattr(slip, "start_date"):
        date_parts = getattr(slip, "start_date", "").split("-")
        if len(date_parts) >= 2:
            return int(date_parts[0]), int(date_parts[1])

    # Default to current year and month if not found
    now = datetime.now()
    return now.year, now.month


def is_december_calculation(slip: Any) -> bool:
    """
    Determine if this slip should use December calculation logic.
    Returns True if month is December or is_december_override flag is set.
    """
    # Check explicit override flag
    if getattr(slip, "is_december_override", 0):
        return True

    # Check if month is December
    _, month = get_slip_year_month(slip)
    return month == 12


def update_slip_fields(slip: Any, values: Dict[str, Any]) -> None:
    """Update salary slip fields with calculated values."""
    for field, value in values.items():
        if hasattr(slip, field):
            setattr(slip, field, value)


def calculate_monthly_pph_progressive(slip: Any) -> Dict[str, Any]:
    """
    Calculate PPh 21 using progressive rates for non-December months.
    """
    tax_status = get_tax_status(slip)
    gross_pay = float(getattr(slip, "gross_pay", 0))
    biaya_jabatan = min(gross_pay * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX)
    total_bpjs = float(getattr(slip, "total_bpjs", 0))

    netto = gross_pay - biaya_jabatan - total_bpjs
    ptkp = get_ptkp_value(tax_status)
    annual_netto = netto * MONTHS_PER_YEAR
    pkp = max(0, annual_netto - ptkp)
    annual_tax, tax_details = calculate_progressive_tax(pkp)
    monthly_tax = annual_tax / MONTHS_PER_YEAR

    update_slip_fields(slip, {"biaya_jabatan": biaya_jabatan, "netto": netto, "pph21": monthly_tax})

    result = {
        "tax_method": "PROGRESSIVE",
        "tax_status": tax_status,
        "gross_pay": gross_pay,
        "biaya_jabatan": biaya_jabatan,
        "total_bpjs": total_bpjs,
        "monthly_netto": netto,
        "annual_netto": annual_netto,
        "ptkp": ptkp,
        "pkp": pkp,
        "annual_tax": annual_tax,
        "monthly_tax": monthly_tax,
        "tax_details": tax_details,
    }

    employee_id = getattr(slip, "employee", "unknown")
    logger.debug(f"Monthly PPh calculation for {employee_id}: {result}")
    return result


def calculate_december_pph(slip: Any) -> Dict[str, Any]:
    """
    Calculate year-end tax correction for December.
    Uses actual YTD income for more accurate annual tax calculation.
    """
    is_december = is_december_calculation(slip)
    if not is_december:
        logger.info(
            f"Non-December month detected for {getattr(slip, 'employee', 'unknown')}, using monthly calculation"
        )
        return calculate_monthly_pph_progressive(slip)

    tax_status = get_tax_status(slip)
    current_gross = float(getattr(slip, "gross_pay", 0))
    current_bpjs = float(getattr(slip, "total_bpjs", 0))
    ytd = get_ytd_totals(slip)
    annual_gross = ytd.get("gross", 0) + current_gross
    annual_bpjs = ytd.get("bpjs", 0) + current_bpjs

    annual_biaya_jabatan = min(annual_gross * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX * 12)
    annual_netto = annual_gross - annual_biaya_jabatan - annual_bpjs
    ptkp = get_ptkp_value(tax_status)
    pkp = max(0, annual_netto - ptkp)
    annual_tax, tax_details = calculate_progressive_tax(pkp)
    ytd_tax_paid = ytd.get("pph21", 0)
    correction = annual_tax - ytd_tax_paid

    monthly_biaya_jabatan = annual_biaya_jabatan / 12
    monthly_netto = annual_netto / 12

    update_slip_fields(
        slip,
        {
            "biaya_jabatan": monthly_biaya_jabatan,
            "netto": monthly_netto,
            "koreksi_pph21": correction,
            "pph21": correction,
        },
    )

    result = {
        "tax_method": "PROGRESSIVE_DECEMBER",
        "tax_status": tax_status,
        "current_gross": current_gross,
        "current_bpjs": current_bpjs,
        "ytd_gross": ytd.get("gross", 0),
        "ytd_bpjs": ytd.get("bpjs", 0),
        "ytd_tax_paid": ytd_tax_paid,
        "annual_gross": annual_gross,
        "annual_bpjs": annual_bpjs,
        "annual_biaya_jabatan": annual_biaya_jabatan,
        "annual_netto": annual_netto,
        "ptkp": ptkp,
        "pkp": pkp,
        "annual_tax": annual_tax,
        "correction": correction,
        "tax_details": tax_details,
        "is_december_override": getattr(slip, "is_december_override", 0),
    }

    employee_id = getattr(slip, "employee", "unknown")
    logger.debug(f"December PPh calculation for {employee_id}: {result}")
    return result
