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

from payroll_indonesia.config.config import get_live_config
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
                    
                    brackets.append({
                        "income_from": income_from,
                        "income_to": income_to,
                        "tax_rate": tax_rate,
                    })
            except Exception as e:
                logger.warning(f"Error parsing progressive_rates_json: {str(e)}")
        
        # Fallback to tax_bracket_table if progressive_rates_json is not available
        if not brackets and hasattr(settings, "tax_bracket_table") and settings.tax_bracket_table:
            for row in settings.tax_bracket_table:
                brackets.append({
                    "income_from": flt(row.income_from),
                    "income_to": flt(row.income_to),
                    "tax_rate": flt(row.tax_rate),
                })
        
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
            logger.warning(f"Calculated tax ({tax}) is more than 50% of PKP ({pkp}). This seems incorrect.")
            
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
    Extract year and month from salary slip start date.

    Args:
        slip: The Salary Slip document

    Returns:
        Tuple[int, int]: Year and month
    """
    try:
        # Try to get from start_date
        if hasattr(slip, "start_date") and slip.start_date:
            date_obj = getdate(slip.start_date)
            return date_obj.year, date_obj.month

        # Try to get from posting_date
        if hasattr(slip, "posting_date") and slip.posting_date:
            date_obj = getdate(slip.posting_date)
            return date_obj.year, date_obj.month

        # Default to current year and month if not found
        now = datetime.now()
        logger.warning(
            f"No date found in slip {getattr(slip, 'name', 'unknown')}. "
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

    Args:
        slip: The Salary Slip document

    Returns:
        bool: True if month is December or is_december_override flag is set
    """
    try:
        # Check explicit override flag
        if cint(getattr(slip, "is_december_override", 0)) == 1:
            logger.debug(f"December override flag set for slip {getattr(slip, 'name', 'unknown')}")
            return True

        # Check if month is December
        _, month = get_slip_year_month(slip)
        is_dec = month == 12

        if is_dec:
            logger.debug(f"December month detected for slip {getattr(slip, 'name', 'unknown')}")

        return is_dec

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
                            
                            # Cache the result
                            cache_utils.set_cache(cache_key, rate, ttl=3600)
                            return rate
            except Exception as e:
                logger.warning(f"Error parsing ter_rates_json: {str(e)}")
        
        # Fallback to ter_rate_table if ter_rates_json not available or parsing failed
        if hasattr(settings, "ter_rate_table") and settings.ter_rate_table:
            # Filter rows by TER category
            category_rows = [row for row in settings.ter_rate_table if row.status_pajak.upper() == ter_category]
            
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
                            f"Found TER rate {rate * 100}% for category {ter_category}, "
                            f"income {monthly_income}"
                        )
                        # Cache the result
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
            f"No matching TER rate found for category {ter_category}, "
            f"income {monthly_income}. Using default: {rate * 100}%"
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
        ptkp_to_ter = cfg.get("ptkp_to_ter_mapping", {})

        # Use configuration mapping if available
        if ptkp_code in ptkp_to_ter:
            category = ptkp_to_ter[ptkp_code]
            cache_utils.set_cache(cache_key, category, ttl=3600)
            return category

        # Default mapping logic
        prefix = ptkp_code[:2] if len(ptkp_code) >= 2 else ptkp_code
        suffix = ptkp_code[2:] if len(ptkp_code) >= 3 else "0"

        category = None
        if ptkp_code == "TK0":
            category = "TER A"
        elif prefix == "TK" and suffix in ["1", "2", "3"]:
            category = "TER B"
        elif prefix == "K" and suffix == "0":
            category = "TER B"
        elif prefix == "K" and suffix in ["1", "2", "3"]:
            category = "TER C"
        elif prefix == "HB":  # Single parent
            category = "TER C"
        else:
            # Default to highest category
            logger.warning(f"Unknown PTKP code '{ptkp_code}', defaulting to TER C")
            category = "TER C"
        
        # Cache the result
        cache_utils.set_cache(cache_key, category, ttl=3600)
        return category

    except Exception as e:
        logger.exception(f"Error getting TER category for {ptkp_code}: {str(e)}")
        return "TER C"


def calculate_monthly_pph_with_ter(
    *, ter_category: str, gross_pay: float, **kwargs
) -> Dict[str, Any]:
    """
    Calculate monthly PPh 21 using TER category.
    
    Args:
        ter_category: TER category (TER A, TER B, or TER C)
        gross_pay: Monthly gross pay (not annualized)
        **kwargs: Additional arguments (slip, etc.)
        
    Returns:
        Dict[str, Any]: Calculation results
    """
    try:
        # Note: No annualization of gross_pay here - use monthly amount directly
        ter_rate = get_ter_rate(ter_category, gross_pay)
        monthly_tax = flt(gross_pay * ter_rate, 2)

        result = {
            "tax_method": "TER",
            "ter_category": ter_category,
            "gross_pay": gross_pay,
            "annual_taxable_income": gross_pay * 12,  # Just for reference
            "ter_rate": ter_rate,
            "monthly_tax": monthly_tax,
        }

        slip = kwargs.get("slip")
        if slip:
            update_slip_fields(
                slip,
                {
                    "monthly_gross_for_ter": gross_pay,
                    "annual_taxable_income": gross_pay * 12,  # Just for reference
                    "ter_category": ter_category,
                    "ter_rate": ter_rate * 100,  # Store as percentage
                    "is_using_ter": 1,
                    "pph21": monthly_tax,
                },
            )
            # Also update any PPh 21 component
            _update_pph21_component(slip, monthly_tax)

        return result
    
    except Exception as e:
        logger.exception(f"Error in TER calculation: {str(e)}")
        return {
            "tax_method": "TER",
            "ter_category": ter_category,
            "gross_pay": gross_pay,
            "ter_rate": 0.0,
            "monthly_tax": 0.0,
            "error": str(e)
        }


def calculate_monthly_pph_progressive(slip: Any) -> Dict[str, Any]:
    """
    Calculate PPh 21 using progressive rates for non-December months.
    Checks tax calculation method from settings and uses TER if configured.

    Args:
        slip: The Salary Slip document

    Returns:
        Dict[str, Any]: Calculation results
    """
    try:
        # Check tax calculation method from settings
        settings = frappe.get_cached_doc("Payroll Indonesia Settings")
        tax_method = getattr(settings, "tax_calculation_method", "PROGRESSIVE")
        
        # Use TER if configured
        if tax_method == "TER" and cint(getattr(settings, "use_ter", 0)) == 1:
            tax_status = get_tax_status(slip)
            ter_category = get_ter_category(tax_status)
            gross_pay = flt(getattr(slip, "gross_pay", 0))
            
            # Calculate using TER method
            return calculate_monthly_pph_with_ter(
                ter_category=ter_category,
                gross_pay=gross_pay,
                slip=slip
            )
        
        # Continue with progressive method
        # Initialize result with zeros
        result = {
            "tax_method": "PROGRESSIVE",
            "tax_status": "TK0",
            "gross_pay": 0.0,
            "biaya_jabatan": 0.0,
            "total_bpjs": 0.0,
            "monthly_netto": 0.0,
            "annual_netto": 0.0,
            "ptkp": 0.0,
            "pkp": 0.0,
            "annual_tax": 0.0,
            "monthly_tax": 0.0,
            "tax_details": [],
        }

        # Get tax status
        tax_status = get_tax_status(slip)
        result["tax_status"] = tax_status

        # Get gross pay
        gross_pay = flt(getattr(slip, "gross_pay", 0))
        if gross_pay <= 0:
            logger.warning(
                f"Zero or negative gross pay for slip {getattr(slip, 'name', 'unknown')}"
            )

        result["gross_pay"] = gross_pay

        # Calculate biaya jabatan
        biaya_jabatan = min(gross_pay * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX)
        result["biaya_jabatan"] = biaya_jabatan

        # Get total BPJS employee
        total_bpjs = flt(getattr(slip, "total_bpjs", 0))
        result["total_bpjs"] = total_bpjs

        # Calculate netto
        netto = gross_pay - biaya_jabatan - total_bpjs
        result["monthly_netto"] = netto

        # Calculate annual values
        annual_netto = netto * MONTHS_PER_YEAR
        result["annual_netto"] = annual_netto

        # Get PTKP
        ptkp = get_ptkp_value(tax_status)
        result["ptkp"] = ptkp

        # Calculate PKP
        pkp = max(0, annual_netto - ptkp)
        result["pkp"] = pkp

        # Calculate tax
        annual_tax, tax_details = calculate_progressive_tax(pkp)
        result["annual_tax"] = annual_tax
        result["tax_details"] = tax_details

        # Calculate monthly tax
        monthly_tax = annual_tax / MONTHS_PER_YEAR
        result["monthly_tax"] = flt(monthly_tax, 2)

        # Update slip fields
        update_slip_fields(
            slip, {"biaya_jabatan": biaya_jabatan, "netto": netto, "pph21": monthly_tax}
        )

        # Also update any PPh 21 component
        _update_pph21_component(slip, monthly_tax)

        employee_id = getattr(slip, "employee", "unknown")
        logger.debug(f"Monthly PPh calculation for {employee_id}: {result}")
        return result

    except Exception as e:
        logger.exception(f"Error calculating monthly PPh: {str(e)}")
        # Set fields to zero in case of error
        update_slip_fields(slip, {"biaya_jabatan": 0, "netto": 0, "pph21": 0})
        return {
            "tax_method": "PROGRESSIVE",
            "tax_status": get_tax_status(slip),
            "gross_pay": flt(getattr(slip, "gross_pay", 0)),
            "biaya_jabatan": 0,
            "total_bpjs": 0,
            "monthly_netto": 0,
            "annual_netto": 0,
            "ptkp": 0,
            "pkp": 0,
            "annual_tax": 0,
            "monthly_tax": 0,
            "tax_details": [],
            "error": str(e),
        }


def calculate_december_pph(slip: Any) -> Dict[str, Any]:
    """
    Calculate year-end tax correction for December.
    Uses actual YTD income for more accurate annual tax calculation.
    Checks tax calculation method from settings and uses TER if configured.

    Args:
        slip: The Salary Slip document

    Returns:
        Dict[str, Any]: Calculation results
    """
    try:
        # Check if it's actually December
        is_december = is_december_calculation(slip)
        if not is_december:
            logger.info(
                f"Non-December month detected for {getattr(slip, 'employee', 'unknown')}, "
                f"using monthly calculation"
            )
            return calculate_monthly_pph_progressive(slip)

        # Check tax calculation method from settings
        settings = frappe.get_cached_doc("Payroll Indonesia Settings")
        tax_method = getattr(settings, "tax_calculation_method", "PROGRESSIVE")
        
        # Use TER if configured, even for December
        if tax_method == "TER" and cint(getattr(settings, "use_ter", 0)) == 1:
            tax_status = get_tax_status(slip)
            ter_category = get_ter_category(tax_status)
            gross_pay = flt(getattr(slip, "gross_pay", 0))
            
            # For December with TER, we still use the simple monthly calculation
            # but we might apply additional logic if needed in the future
            result = calculate_monthly_pph_with_ter(
                ter_category=ter_category,
                gross_pay=gross_pay,
                slip=slip
            )
            # Add flag to indicate this was a December calculation with TER
            result["is_december"] = True
            return result

        # Continue with progressive December method
        # Initialize result with zeros
        result = {
            "tax_method": "PROGRESSIVE_DECEMBER",
            "tax_status": "TK0",
            "current_gross": 0.0,
            "current_bpjs": 0.0,
            "ytd_gross": 0.0,
            "ytd_bpjs": 0.0,
            "ytd_tax_paid": 0.0,
            "annual_gross": 0.0,
            "annual_bpjs": 0.0,
            "annual_biaya_jabatan": 0.0,
            "annual_netto": 0.0,
            "ptkp": 0.0,
            "pkp": 0.0,
            "annual_tax": 0.0,
            "correction": 0.0,
            "tax_details": [],
            "is_december_override": 0,
        }

        # Get tax status
        tax_status = get_tax_status(slip)
        result["tax_status"] = tax_status

        # Get current values
        current_gross = flt(getattr(slip, "gross_pay", 0))
        current_bpjs = flt(getattr(slip, "total_bpjs", 0))
        result["current_gross"] = current_gross
        result["current_bpjs"] = current_bpjs

        # Get YTD values
        ytd = get_ytd_totals(slip)
        result["ytd_gross"] = ytd.get("gross", 0)
        result["ytd_bpjs"] = ytd.get("bpjs", 0)
        result["ytd_tax_paid"] = ytd.get("pph21", 0)

        # Calculate annual values
        annual_gross = ytd.get("gross", 0) + current_gross
        annual_bpjs = ytd.get("bpjs", 0) + current_bpjs
        result["annual_gross"] = annual_gross
        result["annual_bpjs"] = annual_bpjs

        # Calculate annual biaya jabatan
        annual_biaya_jabatan = min(
            annual_gross * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX * 12
        )
        result["annual_biaya_jabatan"] = annual_biaya_jabatan

        # Calculate annual netto
        annual_netto = annual_gross - annual_biaya_jabatan - annual_bpjs
        result["annual_netto"] = annual_netto

        # Get PTKP
        ptkp = get_ptkp_value(tax_status)
        result["ptkp"] = ptkp

        # Calculate PKP
        pkp = max(0, annual_netto - ptkp)
        result["pkp"] = pkp

        # Calculate tax
        annual_tax, tax_details = calculate_progressive_tax(pkp)
        result["annual_tax"] = annual_tax
        result["tax_details"] = tax_details

        # Calculate correction
        ytd_tax_paid = ytd.get("pph21", 0)
        correction = annual_tax - ytd_tax_paid
        result["correction"] = flt(correction, 2)

        # Calculate monthly values for display
        monthly_biaya_jabatan = annual_biaya_jabatan / 12
        monthly_netto = annual_netto / 12

        # Set December override flag
        result["is_december_override"] = cint(getattr(slip, "is_december_override", 0))

        # Update slip fields
        update_slip_fields(
            slip,
            {
                "biaya_jabatan": monthly_biaya_jabatan,
                "netto": monthly_netto,
                "koreksi_pph21": correction,
                "pph21": correction,
            },
        )

        # Also update any PPh 21 component
        _update_pph21_component(slip, correction)

        employee_id = getattr(slip, "employee", "unknown")
        logger.debug(f"December PPh calculation for {employee_id}: {result}")
        return result

    except Exception as e:
        logger.exception(f"Error calculating December PPh: {str(e)}")
        # Set fields to zero in case of error
        update_slip_fields(
            slip,
            {
                "biaya_jabatan": 0,
                "netto": 0,
                "koreksi_pph21": 0,
                "pph21": 0,
            },
        )
        return {
            "tax_method": "PROGRESSIVE_DECEMBER",
            "tax_status": get_tax_status(slip),
            "current_gross": flt(getattr(slip, "gross_pay", 0)),
            "current_bpjs": flt(getattr(slip, "total_bpjs", 0)),
            "ytd_gross": 0,
            "ytd_bpjs": 0,
            "ytd_tax_paid": 0,
            "annual_gross": 0,
            "annual_bpjs": 0,
            "annual_biaya_jabatan": 0,
            "annual_netto": 0,
            "ptkp": 0,
            "pkp": 0,
            "annual_tax": 0,
            "correction": 0,
            "tax_details": [],
            "is_december_override": cint(getattr(slip, "is_december_override", 0)),
            "error": str(e),
        }


def _update_pph21_component(slip: Any, tax_amount: float) -> None:
    """
    Update PPh 21 component in deductions.

    Args:
        slip: The Salary Slip document
        tax_amount: The tax amount to set
    """
    try:
        if not hasattr(slip, "deductions"):
            return

        for deduction in slip.deductions:
            if getattr(deduction, "salary_component", "") == "PPh 21":
                deduction.amount = tax_amount
                logger.debug(
                    f"Updated PPh 21 component to {tax_amount} in slip {getattr(slip, 'name', 'unknown')}"
                )
                break

    except Exception as e:
        logger.exception(f"Error updating PPh 21 component: {str(e)}")


# Unit tests
def _run_tests():
    """Run unit tests for tax calculations"""
    print("Running tax calculator unit tests...")
    
    # TER rate test
    ter_test_category = "TER B"
    ter_test_income = 10000000  # 10 million monthly
    ter_test_rate = get_ter_rate(ter_test_category, ter_test_income)
    ter_test_expected_rate = 0.025  # 2.5%
    print(f"TER rate test: get_ter_rate({ter_test_category}, {ter_test_income}) = {ter_test_rate}")
    assert abs(ter_test_rate - ter_test_expected_rate) < 0.001, "TER rate calculation failed"
    
    # TER tax test
    ter_test_tax = ter_test_income * ter_test_rate
    ter_test_tax_expected = 250000  # 250,000
    print(f"TER tax test: {ter_test_income} * {ter_test_rate} = {ter_test_tax}")
    assert abs(ter_test_tax - ter_test_tax_expected) < 100, "TER tax calculation failed"
    
    # TER category test
    ptkp_code = "TK1"
    ter_category = get_ter_category(ptkp_code)
    expected_category = "TER B"
    print(f"TER category test: get_ter_category({ptkp_code}) = {ter_category}")
    assert ter_category == expected_category, "TER category mapping failed"
    
    # Progressive test
    pkp_test = 60000000  # 60 million annual
    tax_test, _ = calculate_progressive_tax(pkp_test)
    tax_test_expected = 3000000  # 5% of 60 million = 3 million
    print(f"Progressive test: tax on {pkp_test} = {tax_test}")
    assert abs(tax_test - tax_test_expected) < 100, "Progressive tax calculation failed"
    
    # Progressive brackets test
    brackets = get_tax_brackets()
    print(f"Tax brackets: {brackets}")
    assert len(brackets) >= 4, "Failed to get proper tax brackets"
    
    # Tax < 50% of income test
    high_income = 100000000  # 100 million annual
    high_tax, _ = calculate_progressive_tax(high_income)
    print(f"High income test: tax on {high_income} = {high_tax}")
    assert high_tax < high_income * 0.5, "Tax exceeds 50% of income"
    
    print("All tests passed!")
    return True


# Only run tests in development mode
if frappe.conf.get("developer_mode") and __name__ == "__main__":
    _run_tests()