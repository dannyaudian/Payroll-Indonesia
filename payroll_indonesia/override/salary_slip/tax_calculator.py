# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
Tax calculator module - PPh 21 (progresif & tahunan)
"""

import json
import logging
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime

import frappe
from frappe.utils import flt, cint, getdate

from payroll_indonesia.config.config import get_live_config, get_component_tax_effect
from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR,
    BIAYA_JABATAN_PERCENT,
    BIAYA_JABATAN_MAX,
)
from payroll_indonesia.utilities import cache_utils

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
    "calculate_monthly_pph_with_ter",
    "get_ter_rate",
    "get_ter_category",
    "categorize_components_by_tax_effect",
]


def get_tax_brackets() -> List[Dict[str, Any]]:
    """
    Get progressive tax brackets from Payroll Indonesia Settings.
    Returns sorted list of brackets by income_from.

    Returns:
        List[Dict[str, Any]]: List of tax brackets with income_from, income_to, and tax_rate
    """
    try:
        # Try to get from cache first
        cache_key = "tax:brackets"
        cached_brackets = cache_utils.get_cache(cache_key)
        if cached_brackets:
            return cached_brackets

        # Get from settings
        settings = frappe.get_cached_doc("Payroll Indonesia Settings")
        brackets = []

        # Check if progressive_rates_json exists and use it
        if hasattr(settings, "progressive_rates_json") and settings.progressive_rates_json:
            try:
                # If it's a string, parse it as JSON
                if isinstance(settings.progressive_rates_json, str):
                    json_brackets = json.loads(settings.progressive_rates_json)
                else:
                    json_brackets = settings.progressive_rates_json

                for bracket in json_brackets:
                    # Ensure we have all necessary fields
                    income_from = flt(bracket.get("income_from", 0))
                    income_to = flt(bracket.get("income_to", 0))
                    tax_rate = flt(bracket.get("tax_rate", 0))
                    # Convert rate to percentage if stored as decimal
                    tax_rate = tax_rate * 100 if tax_rate <= 1 else tax_rate

                    brackets.append(
                        {
                            "income_from": income_from,
                            "income_to": income_to,
                            "tax_rate": tax_rate,
                        }
                    )
            except Exception as e:
                logger.warning(f"Error parsing progressive_rates_json: {str(e)}")

        # Fallback to tax_bracket_table if progressive_rates_json is not available
        if not brackets and hasattr(settings, "tax_bracket_table") and settings.tax_bracket_table:
            for row in settings.tax_bracket_table:
                brackets.append(
                    {
                        "income_from": flt(row.income_from),
                        "income_to": flt(row.income_to),
                        "tax_rate": flt(row.tax_rate),
                    }
                )

        # If no brackets in settings, try config
        if not brackets:
            cfg = get_live_config()
            brackets = cfg.get("tax", {}).get("brackets", [])

        # Sort brackets by income_from
        if brackets:
            sorted_brackets = sorted(brackets, key=lambda x: float(x.get("income_from", 0)))
            # Cache the result for 1 hour
            cache_utils.set_cache(cache_key, sorted_brackets, ttl=3600)
            return sorted_brackets

        # Default tax brackets (as of 2025)
        default_brackets = [
            {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
            {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
            {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
            {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
            {"income_from": 5000000000, "income_to": 0, "tax_rate": 35},
        ]
        logger.warning("No tax brackets found in settings or config. Using default brackets.")
        # Cache the default brackets
        cache_utils.set_cache(cache_key, default_brackets, ttl=3600)
        return default_brackets

    except Exception as e:
        logger.exception(f"Error getting tax brackets: {str(e)}")
        # Return default brackets on error
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

    Args:
        tax_status: Tax status code (e.g., TK0, K1)

    Returns:
        float: Annual PTKP amount
    """
    try:
        if not tax_status:
            logger.warning("Empty tax status provided. Using default TK0.")
            tax_status = "TK0"

        # Try to get from cache first
        cache_key = f"tax:ptkp:{tax_status}"
        cached_value = cache_utils.get_cache(cache_key)
        if cached_value is not None:
            return cached_value

        # Get from settings
        settings = frappe.get_cached_doc("Payroll Indonesia Settings")
        ptkp_value = 0

        # Get from PTKP table
        if hasattr(settings, "ptkp_table") and settings.ptkp_table:
            for row in settings.ptkp_table:
                if row.ptkp_status and row.ptkp_status.upper() == tax_status.upper():
                    ptkp_value = flt(row.ptkp_value)
                    # Cache the result for 1 hour
                    cache_utils.set_cache(cache_key, ptkp_value, ttl=3600)
                    return ptkp_value

        # If not found in settings, try config
        cfg = get_live_config()
        ptkp_values = cfg.get("ptkp", {})

        if tax_status in ptkp_values:
            ptkp_value = float(ptkp_values[tax_status])
            # Cache the result
            cache_utils.set_cache(cache_key, ptkp_value, ttl=3600)
            return ptkp_value

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

        if tax_status not in default_values:
            logger.warning(f"Unknown tax status: {tax_status}. Using TK0 as default.")
            tax_status = "TK0"

        ptkp_value = float(default_values.get(tax_status, 54000000))
        # Cache the result
        cache_utils.set_cache(cache_key, ptkp_value, ttl=3600)
        return ptkp_value

    except Exception as e:
        logger.exception(f"Error getting PTKP value for {tax_status}: {str(e)}")
        # Return default TK0 value on error
        return 54000000


def calculate_progressive_tax(pkp: float) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Calculate PPh 21 using progressive method.

    Args:
        pkp: Penghasilan Kena Pajak (taxable income)

    Returns:
        Tuple[float, List[Dict[str, Any]]]: Total tax and detailed breakdown per bracket
    """
    try:
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

        # Ensure tax is not unreasonably high (basic sanity check)
        if tax > pkp * 0.5:
            logger.warning(
                f"Calculated tax ({tax}) is more than 50% of PKP ({pkp}). This seems incorrect."
            )

        return flt(tax, 2), details

    except Exception as e:
        logger.exception(f"Error calculating progressive tax for PKP {pkp}: {str(e)}")
        # Return zero on error
        return 0.0, []


def get_tax_status(slip: Any) -> str:
    """
    Extract tax status from employee document or return default.

    Args:
        slip: The Salary Slip document

    Returns:
        str: Tax status code (e.g., TK0, K1)
    """
    try:
        default_status = "TK0"

        # Try to get from status_pajak field directly
        if hasattr(slip, "status_pajak") and slip.status_pajak:
            return slip.status_pajak

        # Try to get from employee_doc field
        employee = getattr(slip, "employee_doc", None)
        if employee and hasattr(employee, "status_pajak") and employee.status_pajak:
            return employee.status_pajak

        # If employee_doc not available, try to get directly from employee
        if hasattr(slip, "employee") and slip.employee:
            try:
                employee_id = slip.employee
                employee_doc = frappe.get_doc("Employee", employee_id)
                if hasattr(employee_doc, "status_pajak") and employee_doc.status_pajak:
                    # Set employee_doc for future reference
                    slip.employee_doc = employee_doc
                    return employee_doc.status_pajak
            except Exception as e:
                logger.warning(
                    f"Could not load employee {getattr(slip, 'employee', 'unknown')}: {e}"
                )

        # If we got here, use default
        logger.warning(
            f"No tax status found for employee {getattr(slip, 'employee', 'unknown')}. "
            f"Using default: {default_status}"
        )
        return default_status

    except Exception as e:
        logger.exception(f"Error getting tax status: {str(e)}")
        return "TK0"


def get_ytd_totals(slip: Any) -> Dict[str, float]:
    """
    Get year-to-date totals for gross pay, BPJS, and PPh 21.
    Aggregates data from all salary slips in the same fiscal year up to the slip's posting date.

    Args:
        slip: The salary slip object

    Returns:
        Dict[str, float]: Dictionary with YTD totals for gross, bpjs, and pph21
    """
    try:
        year, _ = get_slip_year_month(slip)
        employee = getattr(slip, "employee", None)
        posting_date = getattr(slip, "posting_date", None)
        slip_name = getattr(slip, "name", "unknown")

        if not employee or not posting_date:
            logger.warning(f"Missing employee or posting_date in slip {slip_name}, returning zeros")
            return {"gross": 0.0, "bpjs": 0.0, "pph21": 0.0}

        logger.debug(f"Fetching YTD totals for employee {employee}, year {year}")

        # Check cache first
        cache_key = f"ytd_totals:{employee}:{year}:{posting_date}"
        cached_result = cache_utils.get_cache(cache_key)
        if cached_result:
            logger.debug(f"Using cached YTD totals for {employee}")
            return cached_result

        # Default result if no data is found
        result = {"gross": 0.0, "bpjs": 0.0, "pph21": 0.0}

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

        # Query for YTD totals (excluding current slip)
        ytd_data = frappe.db.sql(
            f"""
            SELECT {', '.join(select_fields)}
            FROM `tabSalary Slip`
            WHERE docstatus = 1
              AND employee = %s
              AND posting_date <= %s
              AND YEAR(posting_date) = %s
              AND name != %s
            """,
            (employee, posting_date, year, slip_name),
            as_dict=1,
        )

        if ytd_data and len(ytd_data) > 0:
            # Update result with non-null values from query
            for key in result.keys():
                if key in ytd_data[0] and ytd_data[0][key] is not None:
                    result[key] = flt(ytd_data[0][key])

        # Cache the result
        cache_utils.set_cache(cache_key, result, expires_in_sec=300)

        logger.debug(f"YTD totals for {employee}: {result}")
        return result

    except Exception as e:
        logger.exception(f"Error calculating YTD totals: {str(e)}")
        return {"gross": 0.0, "bpjs": 0.0, "pph21": 0.0}


def get_slip_year_month(slip: Any) -> Tuple[int, int]:
    """
    Extract year and month from salary slip dates.

    Args:
        slip: The Salary Slip document

    Returns:
        Tuple[int, int]: Year and month
    """
    try:
        # Use posting_date as the primary reference for year and month
        if hasattr(slip, "posting_date") and slip.posting_date:
            date_obj = getdate(slip.posting_date)
            return date_obj.year, date_obj.month

        # Fall back to current date when posting_date is unavailable
        now = datetime.now()
        logger.warning(
            f"Posting date not found in slip {getattr(slip, 'name', 'unknown')}. "
            f"Using current date: {now.year}-{now.month}"
        )
        return now.year, now.month

    except Exception as e:
        logger.exception(f"Error getting slip year/month: {str(e)}")
        now = datetime.now()
        return now.year, now.month


def is_december_calculation(slip: Any) -> bool:
    """
    Determine if this slip should use December calculation logic.

    Only checks the is_december_override flag on the slip.

    Args:
        slip: The Salary Slip document

    Returns:
        bool: True if is_december_override flag is set
    """
    try:
        # Prioritize Payroll Entry flag if available
        payroll_entry = getattr(slip, "payroll_entry", None)
        if payroll_entry:
            try:
                entry_doc = (
                    frappe.get_doc("Payroll Entry", payroll_entry)
                    if isinstance(payroll_entry, str)
                    else payroll_entry
                )
                override = cint(getattr(entry_doc, "is_december_override", 0)) == 1
                if override:
                    logger.debug(
                        f"December override flag set via Payroll Entry for slip {getattr(slip, 'name', 'unknown')}"
                    )
                return override
            except Exception as e:
                logger.warning(
                    f"Unable to read Payroll Entry for {getattr(slip, 'name', 'unknown')}: {e}"
                )

        # Fallback to slip field
        override = cint(getattr(slip, "is_december_override", 0)) == 1
        if override:
            logger.debug(f"December override flag set for slip {getattr(slip, 'name', 'unknown')}")
        return override
    except Exception as e:
        logger.exception(f"Error checking December calculation: {str(e)}")
        return False


def update_slip_fields(slip: Any, values: Dict[str, Any]) -> None:
    """
    Update salary slip fields with calculated values.

    Args:
        slip: The Salary Slip document
        values: Dictionary of field name/value pairs to update
    """
    try:
        for field, value in values.items():
            if hasattr(slip, field):
                setattr(slip, field, value)
                logger.debug(f"Updated {field}={value} in slip {getattr(slip, 'name', 'unknown')}")
            else:
                logger.warning(
                    f"Field {field} not found in slip {getattr(slip, 'name', 'unknown')}"
                )

    except Exception as e:
        logger.exception(f"Error updating slip fields: {str(e)}")


def categorize_components_by_tax_effect(slip: Any) -> Dict[str, Dict[str, float]]:
    """
    Categorize salary components by their tax effect type.

    Args:
        slip: The Salary Slip document

    Returns:
        Dict: Components categorized by tax effect type with amounts
    """
    try:
        # Initialize result structure
        result = {
            "penambah_bruto": {},  # Objek Pajak components
            "pengurang_netto": {},  # Tax deduction components
            "tidak_berpengaruh": {},  # Non-taxable components
            "natura_objek": {},  # Taxable benefits in kind
            "natura_non_objek": {},  # Non-taxable benefits in kind
            "total": {
                "penambah_bruto": 0,
                "pengurang_netto": 0,
                "tidak_berpengaruh": 0,
                "natura_objek": 0,
                "natura_non_objek": 0,
            },
        }

        # Process earnings
        if hasattr(slip, "earnings"):
            for earning in slip.earnings:
                component_name = getattr(earning, "salary_component", "")
                amount = flt(getattr(earning, "amount", 0))

                # Skip zero amounts
                if amount <= 0:
                    continue

                # Get tax effect for this earning
                tax_effect = get_component_tax_effect(component_name, "Earning")

                # Categorize based on tax effect
                if tax_effect == "Penambah Bruto/Objek Pajak":
                    result["penambah_bruto"][component_name] = amount
                    result["total"]["penambah_bruto"] += amount
                elif tax_effect == "Pengurang Netto/Tax Deduction":
                    result["pengurang_netto"][component_name] = amount
                    result["total"]["pengurang_netto"] += amount
                elif tax_effect == "Natura/Fasilitas (Objek Pajak)":
                    result["natura_objek"][component_name] = amount
                    result["total"]["natura_objek"] += amount
                elif tax_effect == "Natura/Fasilitas (Non-Objek Pajak)":
                    result["natura_non_objek"][component_name] = amount
                    result["total"]["natura_non_objek"] += amount
                else:  # Tidak Berpengaruh ke Pajak
                    result["tidak_berpengaruh"][component_name] = amount
                    result["total"]["tidak_berpengaruh"] += amount

        # Process deductions
        if hasattr(slip, "deductions"):
            for deduction in slip.deductions:
                component_name = getattr(deduction, "salary_component", "")
                amount = flt(getattr(deduction, "amount", 0))

                # Skip zero amounts
                if amount <= 0:
                    continue

                # Skip PPh 21 itself
                if component_name == "PPh 21":
                    continue

                # Get tax effect for this deduction
                tax_effect = get_component_tax_effect(component_name, "Deduction")

                # Categorize based on tax effect
                if tax_effect == "Penambah Bruto/Objek Pajak":
                    result["penambah_bruto"][component_name] = amount
                    result["total"]["penambah_bruto"] += amount
                elif tax_effect == "Pengurang Netto/Tax Deduction":
                    result["pengurang_netto"][component_name] = amount
                    result["total"]["pengurang_netto"] += amount
                elif tax_effect == "Natura/Fasilitas (Objek Pajak)":
                    result["natura_objek"][component_name] = amount
                    result["total"]["natura_objek"] += amount
                elif tax_effect == "Natura/Fasilitas (Non-Objek Pajak)":
                    result["natura_non_objek"][component_name] = amount
                    result["total"]["natura_non_objek"] += amount
                else:  # Tidak Berpengaruh ke Pajak
                    result["tidak_berpengaruh"][component_name] = amount
                    result["total"]["tidak_berpengaruh"] += amount

        return result

    except Exception as e:
        logger.exception(f"Error categorizing components: {str(e)}")
        # Return empty result on error
        return {
            "penambah_bruto": {},
            "pengurang_netto": {},
            "tidak_berpengaruh": {},
            "natura_objek": {},
            "natura_non_objek": {},
            "total": {
                "penambah_bruto": 0,
                "pengurang_netto": 0,
                "tidak_berpengaruh": 0,
                "natura_objek": 0,
                "natura_non_objek": 0,
            },
        }


def get_ter_rate(ter_category: str, monthly_income: float) -> float:
    """
    Get TER rate based on TER category and monthly income from Payroll Indonesia Settings.

    Args:
        ter_category: TER category (TER A, TER B, or TER C)
        monthly_income: Monthly taxable income (not annualized)

    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    try:
        # Try to get from cache first
        cache_key = f"tax:ter_rate:{ter_category}:{int(monthly_income)}"
        cached_rate = cache_utils.get_cache(cache_key)
        if cached_rate is not None:
            return cached_rate

        # Get from settings
        settings = frappe.get_cached_doc("Payroll Indonesia Settings")

        # Format TER category to handle case differences
        ter_category = ter_category.upper().strip()

        # Try to get rates from ter_rates_json first
        if hasattr(settings, "ter_rates_json") and settings.ter_rates_json:
            try:
                # If it's a string, parse it as JSON
                if isinstance(settings.ter_rates_json, str):
                    ter_rates = json.loads(settings.ter_rates_json)
                else:
                    ter_rates = settings.ter_rates_json

                # Find category in JSON
                if ter_category in ter_rates:
                    category_rates = ter_rates[ter_category]

                    # Find applicable bracket
                    for bracket in category_rates:
                        income_from = flt(bracket.get("income_from", 0))
                        income_to = flt(bracket.get("income_to", 0))
                        is_highest = cint(bracket.get("is_highest_bracket", 0))

                        if monthly_income >= income_from and (
                            is_highest or income_to == 0 or monthly_income < income_to
                        ):
                            # Get rate and convert to decimal if needed
                            rate = flt(bracket.get("rate", 0))
                            rate = rate / 100 if rate > 1 else rate

                            logger.debug(
                                f"Found TER rate {rate * 100}% for category {ter_category} from ter_rates_json, income {monthly_income}"
                            )
                            # Cache the result
                            cache_utils.set_cache(cache_key, rate, ttl=3600)
                            return rate
            except Exception as e:
                logger.warning(f"Error parsing ter_rates_json: {str(e)}")

        # Fallback to ter_rate_table if ter_rates_json not available or parsing failed
        if hasattr(settings, "ter_rate_table") and settings.ter_rate_table:
            # Filter rows by TER category
            category_rows = [
                row for row in settings.ter_rate_table if row.status_pajak.upper() == ter_category
            ]

            if category_rows:
                # Sort by income_from ascending
                sorted_rows = sorted(category_rows, key=lambda x: flt(x.income_from))

                # Find applicable rate based on income
                for row in sorted_rows:
                    income_from = flt(row.income_from)
                    income_to = flt(row.income_to)
                    is_highest = cint(getattr(row, "is_highest_bracket", 0))

                    if monthly_income >= income_from and (
                        is_highest or income_to == 0 or monthly_income < income_to
                    ):
                        # Convert percentage to decimal (e.g., 5% to 0.05)
                        rate = flt(row.rate) / 100.0
                        logger.debug(
                            f"Found TER rate {rate * 100}% for category {ter_category} from ter_rate_table, "
                            f"income {monthly_income}"
                        )
                        # Cache the result
                        cache_utils.set_cache(cache_key, rate, ttl=3600)
                        return rate

        # Try to get rates from live config if still not found
        cfg = get_live_config()
        cfg_rates = cfg.get("tax", {}).get("ter_rates", {})

        if ter_category in cfg_rates:
            category_rates = cfg_rates[ter_category]

            for bracket in category_rates:
                income_from = flt(bracket.get("income_from", 0))
                income_to = flt(bracket.get("income_to", 0))
                is_highest = cint(bracket.get("is_highest_bracket", 0))

                if monthly_income >= income_from and (
                    is_highest or income_to == 0 or monthly_income < income_to
                ):
                    rate = flt(bracket.get("rate", 0))
                    rate = rate / 100 if rate > 1 else rate

                    logger.debug(
                        f"Found TER rate {rate * 100}% for category {ter_category} from config, income {monthly_income}"
                    )
                    cache_utils.set_cache(cache_key, rate, ttl=3600)
                    return rate

        # If no match in settings, use default rates
        default_rates = {
            "TER A": 0.05,  # 5%
            "TER B": 0.10,  # 10%
            "TER C": 0.15,  # 15%
        }

        rate = default_rates.get(ter_category, 0.15)
        logger.warning(
            f"No matching TER rate found for category {ter_category} "
            f"and income {monthly_income}. Using default rate source: defaults ({rate * 100}%)"
        )

        # Cache the result
        cache_utils.set_cache(cache_key, rate, ttl=3600)
        return rate

    except Exception as e:
        logger.exception(f"Error getting TER rate: {str(e)}")
        # Default to 15% on error (higher rate to be safe)
        return 0.15


def get_ter_category(ptkp_code: str) -> str:
    """
    Map PTKP status to TER category based on PMK 168/2023.

    Args:
        ptkp_code: Tax status code (TK0, K1, etc.)

    Returns:
        str: TER category (TER A, TER B, or TER C)
    """
    try:
        # Try to get from cache first
        cache_key = f"tax:ter_category:{ptkp_code}"
        cached_category = cache_utils.get_cache(cache_key)
        if cached_category:
            return cached_category

        # Get mapping from settings
        settings = frappe.get_cached_doc("Payroll Indonesia Settings")

        # Check if we have a mapping table
        if hasattr(settings, "ptkp_ter_mapping_table") and settings.ptkp_ter_mapping_table:
            for row in settings.ptkp_ter_mapping_table:
                if row.ptkp_status and row.ptkp_status.upper() == ptkp_code.upper():
                    category = row.ter_category
                    # Cache the result
                    cache_utils.set_cache(cache_key, category, ttl=3600)
                    return category

        # Try from config
        cfg = get_live_config()
        ter_mapping = cfg.get("tax", {}).get("ter_mapping", {})

        if ptkp_code.upper() in ter_mapping:
            category = ter_mapping[ptkp_code.upper()]
            # Cache the result
            cache_utils.set_cache(cache_key, category, ttl=3600)
            return category

        # Default mapping based on PMK 168/2023
        default_mapping = {
            "TK0": "TER A",
            "TK1": "TER A",
            "TK2": "TER B",
            "TK3": "TER B",
            "K0": "TER A",
            "K1": "TER B",
            "K2": "TER B",
            "K3": "TER C",
            "HB0": "TER C",
            "HB1": "TER C",
            "HB2": "TER C",
            "HB3": "TER C",
        }

        category = default_mapping.get(ptkp_code.upper(), "TER C")
        logger.debug(f"Using default TER category {category} for PTKP status {ptkp_code}")

        # Cache the result
        cache_utils.set_cache(cache_key, category, ttl=3600)
        return category

    except Exception as e:
        logger.exception(f"Error getting TER category: {str(e)}")
        # Default to highest category (TER C) to be safe
        return "TER C"


def calculate_monthly_pph_progressive(slip: Any) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate monthly PPh 21 using standard progressive method.

    Args:
        slip: The Salary Slip document

    Returns:
        Tuple[float, Dict[str, Any]]: PPh 21 amount and calculation details
    """
    try:
        # Get tax status (PTKP code)
        tax_status = get_tax_status(slip)

        # Get gross salary from slip (monthly)
        monthly_gross = flt(getattr(slip, "gross_pay", 0))

        # Get components by tax effect
        tax_components = categorize_components_by_tax_effect(slip)

        # Calculate monthly objek pajak (taxable components)
        monthly_taxable = tax_components["total"]["penambah_bruto"]

        # Add taxable benefits in kind if any
        monthly_taxable += tax_components["total"]["natura_objek"]

        # If using custom formulas, override
        if hasattr(slip, "calculate_taxable_income"):
            try:
                monthly_taxable = slip.calculate_taxable_income()
                logger.debug(f"Using custom taxable income: {monthly_taxable}")
            except Exception as e:
                logger.warning(f"Error in custom taxable income calculation: {e}")

        # Annualize taxable income
        annual_taxable = monthly_taxable * MONTHS_PER_YEAR

        # Deduct Biaya Jabatan (occupation allowance)
        # 5% of gross income, maximum 6,000,000 per year
        biaya_jabatan = min(
            annual_taxable * BIAYA_JABATAN_PERCENT / 100,
            BIAYA_JABATAN_MAX * MONTHS_PER_YEAR,
        )

        # Deduct tax deductible components (annualized)
        tax_deductions = tax_components["total"]["pengurang_netto"] * MONTHS_PER_YEAR

        # Get annual PTKP amount
        annual_ptkp = get_ptkp_value(tax_status)

        # Calculate PKP (taxable income after deductions)
        annual_pkp = max(0, annual_taxable - biaya_jabatan - tax_deductions - annual_ptkp)

        # Round PKP down to nearest 1000
        annual_pkp = flt(annual_pkp, 0)
        annual_pkp = annual_pkp - (annual_pkp % 1000)

        # Calculate tax using progressive method
        annual_tax, tax_details = calculate_progressive_tax(annual_pkp)

        # Calculate monthly tax (annual / 12)
        monthly_tax = annual_tax / MONTHS_PER_YEAR

        # Prepare calculation details
        details = {
            "tax_status": tax_status,
            "ptkp_value": annual_ptkp,
            "monthly_gross": monthly_gross,
            "monthly_taxable": monthly_taxable,
            "annual_taxable": annual_taxable,
            "biaya_jabatan": biaya_jabatan,
            "tax_deductions": tax_deductions,
            "annual_pkp": annual_pkp,
            "annual_tax": annual_tax,
            "monthly_tax": monthly_tax,
            "tax_brackets": tax_details,
            "components": tax_components,
        }

        return flt(monthly_tax, 2), details

    except Exception as e:
        logger.exception(f"Error calculating progressive tax: {str(e)}")
        return 0.0, {}


def calculate_december_pph(slip: Any) -> Tuple[float, Dict[str, Any]]:
    """Calculate December PPh 21 (year-end adjustment)."""
    try:
        employee = getattr(slip, "employee", None)
        if not employee:
            return 0.0, {}

        # Get year from slip
        year, _ = get_slip_year_month(slip)

        # Try to get YTD data from Employee Tax Summary first
        tax_summary = frappe.get_all(
            "Employee Tax Summary",
            filters={"employee": employee, "year": year},
            fields=[
                "ytd_gross_pay",
                "ytd_tax",
                "ytd_bpjs",
                "ytd_taxable_components",
                "ytd_tax_deductions",
                "ytd_tax_correction",
            ],
            limit=1,
        )

        ytd_tax_correction = 0

        if tax_summary:
            # Use data from Employee Tax Summary
            ytd_gross = flt(tax_summary[0].ytd_gross_pay)
            ytd_tax = flt(tax_summary[0].ytd_tax)
            ytd_bpjs = flt(tax_summary[0].ytd_bpjs)
            ytd_taxable = flt(tax_summary[0].ytd_taxable_components)
            ytd_deductions = flt(tax_summary[0].ytd_tax_deductions)
            ytd_tax_correction = flt(tax_summary[0].ytd_tax_correction)
            logger.debug(
                f"Using YTD data from Employee Tax Summary: gross={ytd_gross}, tax={ytd_tax}, correction={ytd_tax_correction}, bpjs={ytd_bpjs}"
            )
        else:
            # Fall back to calculating from salary slips
            ytd = get_ytd_totals(slip)
            ytd_gross = flt(ytd.get("gross", 0))
            ytd_tax = flt(ytd.get("pph21", 0))
            ytd_bpjs = flt(ytd.get("bpjs", 0))
            ytd_taxable = ytd_gross  # Approximate
            ytd_deductions = ytd_bpjs  # Approximate
            ytd_tax_correction = 0

        # Get tax status (PTKP code)
        tax_status = get_tax_status(slip)

        # Get gross salary from slip (monthly)
        monthly_gross = flt(getattr(slip, "gross_pay", 0))

        # Get components by tax effect
        tax_components = categorize_components_by_tax_effect(slip)

        # Calculate monthly objek pajak (taxable components)
        monthly_taxable = tax_components["total"]["penambah_bruto"]

        # Add taxable benefits in kind if any
        monthly_taxable += tax_components["total"]["natura_objek"]

        # If using custom formulas, override
        if hasattr(slip, "calculate_taxable_income"):
            try:
                monthly_taxable = slip.calculate_taxable_income()
                logger.debug(f"Using custom taxable income: {monthly_taxable}")
            except Exception as e:
                logger.warning(f"Error in custom taxable income calculation: {e}")

        # Calculate total annual taxable income
        annual_taxable = ytd_taxable + monthly_taxable

        # Deduct Biaya Jabatan (occupation allowance)
        # 5% of gross income, maximum 6,000,000 per year
        biaya_jabatan = min(
            annual_taxable * BIAYA_JABATAN_PERCENT / 100,
            BIAYA_JABATAN_MAX * MONTHS_PER_YEAR,
        )

        # Deduct annual tax deductions (YTD BPJS + current month tax deductions)
        current_deductions = tax_components["total"]["pengurang_netto"]
        tax_deductions = ytd_deductions + current_deductions

        # Get annual PTKP amount
        annual_ptkp = get_ptkp_value(tax_status)

        # Calculate PKP (taxable income after deductions)
        annual_pkp = max(0, annual_taxable - biaya_jabatan - tax_deductions - annual_ptkp)

        # Round PKP down to nearest 1000
        annual_pkp = flt(annual_pkp, 0)
        annual_pkp = annual_pkp - (annual_pkp % 1000)

        # Calculate tax using progressive method
        annual_tax, tax_details = calculate_progressive_tax(annual_pkp)

        # Calculate December tax (annual tax - YTD tax)
        december_tax = annual_tax - ytd_tax

        # Calculate year-end correction considering prior adjustments
        correction_amount = annual_tax - (ytd_tax + ytd_tax_correction)

        # Prepare calculation details
        details = {
            "tax_status": tax_status,
            "ptkp_value": annual_ptkp,
            "monthly_gross": monthly_gross,
            "monthly_taxable": monthly_taxable,
            "ytd_gross": ytd_gross,
            "ytd_bpjs": ytd_bpjs,
            "ytd_pph21": ytd_tax,
            "ytd_tax_correction": ytd_tax_correction,
            "annual_taxable": annual_taxable,
            "biaya_jabatan": biaya_jabatan,
            "tax_deductions": tax_deductions,
            "annual_pkp": annual_pkp,
            "annual_tax": annual_tax,
            "december_tax": december_tax,
            "correction_amount": correction_amount,
            "tax_brackets": tax_details,
            "components": tax_components,
        }

        return flt(december_tax, 2), details

    except Exception as e:
        logger.exception(f"Error calculating December tax: {str(e)}")
        return 0.0, {}


def calculate_monthly_pph_with_ter(slip: Any) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate monthly PPh 21 using TER (tarif pajak efektif rata-rata) method.

    Args:
        slip: The Salary Slip document

    Returns:
        Tuple[float, Dict[str, Any]]: PPh 21 amount and calculation details
    """
    try:
        # Get tax status (PTKP code)
        tax_status = get_tax_status(slip)

        # Get TER category based on tax status
        ter_category = get_ter_category(tax_status)

        # Get gross salary from slip (monthly)
        monthly_gross = flt(getattr(slip, "gross_pay", 0))

        # Get components by tax effect
        tax_components = categorize_components_by_tax_effect(slip)

        # Calculate monthly objek pajak (taxable components)
        monthly_taxable = tax_components["total"]["penambah_bruto"]

        # Add taxable benefits in kind if any
        monthly_taxable += tax_components["total"]["natura_objek"]

        # If using custom formulas, override
        if hasattr(slip, "calculate_taxable_income"):
            try:
                monthly_taxable = slip.calculate_taxable_income()
                logger.debug(f"Using custom taxable income: {monthly_taxable}")
            except Exception as e:
                logger.warning(f"Error in custom taxable income calculation: {e}")

        # Get TER rate based on category and income
        ter_rate = get_ter_rate(ter_category, monthly_taxable)

        # Monthly gross amount used to determine TER bracket
        monthly_gross_for_ter = monthly_taxable

        # Calculate tax using TER method (simple multiplication)
        monthly_tax = monthly_taxable * ter_rate

        # Prepare calculation details
        details = {
            "tax_status": tax_status,
            "ter_category": ter_category,
            "ter_rate": ter_rate * 100,  # as percentage
            "monthly_gross": monthly_gross,
            "monthly_gross_for_ter": monthly_gross_for_ter,
            "monthly_taxable": monthly_taxable,
            "monthly_tax": monthly_tax,
            "components": tax_components,
        }

        return flt(monthly_tax, 2), details

    except Exception as e:
        logger.exception(f"Error calculating TER tax: {str(e)}")
        return 0.0, {}
