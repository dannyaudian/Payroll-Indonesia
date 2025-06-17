# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-19 08:23:17 by dannyaudian

"""
Core TER and tax calculation logic for Indonesian payroll.

This module contains the core business logic for:
1. TER rate determination and calculation
2. Progressive tax calculation
3. Annual tax calculation
4. PTKP mapping and lookup
5. Tax bracket processing

These functions are kept independent of UI/document manipulation
and can be imported by other modules without causing circular dependencies.
"""

import frappe
from frappe.utils import flt, getdate, cint
from typing import Dict, Optional

# Import cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value

# Import constants
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR,
    CACHE_LONG,
    CACHE_MEDIUM,
    BIAYA_JABATAN_PERCENT,
    BIAYA_JABATAN_MAX,
    TAX_DETECTION_THRESHOLD,
    ANNUAL_DETECTION_FACTOR,
    SALARY_BASIC_FACTOR,
)

# Import TER category mapping from pph_ter (single source of truth)
from payroll_indonesia.payroll_indonesia.tax.pph_ter import map_ptkp_to_ter_category


def log_tax_logic_error(error_type: str, message: str, data: Optional[Dict] = None) -> None:
    """
    Helper function to log tax logic related errors consistently

    Args:
        error_type: Type of error (e.g., "Annual Detection", "Tax Note")
        message: Error message
        data: Additional data to include in the log
    """
    try:
        # Create clean error title
        title = f"Tax Logic {error_type}"

        # Format message with data if provided
        formatted_message = f"{message}\n\nData: {data}" if data else message

        # Log the error
        frappe.log_error(formatted_message, title)
    except Exception:
        # Fallback to simple logging if the above fails
        try:
            frappe.log_error(message, "Tax Logic Error")
        except Exception:
            # If all else fails, silently fail
            pass


def calculate_progressive_tax(pkp, pph_settings=None):
    """
    Calculate tax using progressive rates

    Args:
        pkp: Penghasilan Kena Pajak (taxable income)
        pph_settings: PPh 21 Settings document (optional)

    Returns:
        tuple: (total_tax, tax_details)
    """
    try:
        # Validate input and convert to float if needed
        try:
            pkp_value = flt(pkp)
        except (ValueError, TypeError):
            log_tax_logic_error("Progressive Tax", f"Invalid PKP value: {pkp}, using 0")
            pkp_value = 0

        # Ensure PKP is non-negative
        if pkp_value < 0:
            log_tax_logic_error(
                "Progressive Tax", f"Negative PKP value {pkp_value} provided, using 0 instead"
            )
            pkp_value = 0

        # Get settings
        if not pph_settings and frappe.db.exists("DocType", "PPh 21 Settings"):
            try:
                pph_settings = frappe.get_cached_doc("PPh 21 Settings")
            except Exception as settings_error:
                log_tax_logic_error(
                    "Settings Retrieval", f"Error retrieving PPh 21 Settings: {str(settings_error)}"
                )
                pph_settings = None

        # First check if bracket_table is directly available as attribute
        bracket_table = []
        if pph_settings and hasattr(pph_settings, "bracket_table"):
            bracket_table = pph_settings.bracket_table

        # If not found or empty, query from database
        if not bracket_table and pph_settings:
            try:
                bracket_table = frappe.db.sql(
                    """
                    SELECT income_from, income_to, tax_rate
                    FROM `tabPPh 21 Tax Bracket`
                    WHERE parent = 'PPh 21 Settings'
                    ORDER BY income_from ASC
                """,
                    as_dict=1,
                )
            except Exception as e:
                log_tax_logic_error("Database Error", f"Error querying tax brackets: {str(e)}")

        # If still not found, use default values
        if not bracket_table:
            # Log using our consistent method
            log_tax_logic_error(
                "Default Values", "No tax brackets found in settings, using default values"
            )

            # Default bracket values if not found - based on PMK 101/2016 and UU HPP 2021
            bracket_table = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35},
            ]

        # Calculate tax using progressive rates
        total_tax = 0
        tax_details = []
        remaining_pkp = pkp_value

        # Sort brackets by income_from to ensure proper tax calculation order
        for bracket in sorted(bracket_table, key=lambda x: flt(x.get("income_from", 0))):
            if remaining_pkp <= 0:
                break

            # Use safe getters with defaults
            income_from = flt(bracket.get("income_from", 0))
            income_to = flt(bracket.get("income_to", 0))
            tax_rate = flt(bracket.get("tax_rate", 0))

            # Handle unlimited upper bracket
            upper_limit = income_to if income_to > 0 else float("inf")
            lower_limit = income_from
            taxable = min(remaining_pkp, upper_limit - lower_limit)

            tax = taxable * (tax_rate / 100)
            total_tax += tax

            if tax > 0:
                tax_details.append({"rate": tax_rate, "taxable": taxable, "tax": tax})

            remaining_pkp -= taxable

        return total_tax, tax_details

    except Exception as e:
        # Log error and return default values
        log_tax_logic_error(
            "Calculation Error", f"Error calculating progressive tax for PKP {pkp}: {str(e)}"
        )
        # Return minimal results rather than raising exception
        return 0, []


def get_ptkp_amount(status_pajak, pph_settings=None):
    """
    Get PTKP amount based on tax status from PPh 21 Settings or defaults
    Enhanced with better validation and error handling

    Args:
        status_pajak: Tax status code (e.g., 'TK0', 'K1', etc.)
        pph_settings: PPh 21 Settings document (optional)

    Returns:
        float: PTKP amount
    """
    try:
        # Validate and normalize status_pajak
        if not status_pajak or not isinstance(status_pajak, str):
            log_tax_logic_error(
                "PTKP",
                f"Empty or invalid tax status provided: {status_pajak}, using TK0 as default",
            )
            status_pajak = "TK0"
        else:
            # Normalize by removing whitespace and converting to uppercase
            status_pajak = status_pajak.strip().upper()
            if not status_pajak:
                status_pajak = "TK0"

        # Use cache for PTKP amount
        cache_key = f"ptkp_amount:{status_pajak}"
        ptkp_amount = get_cached_value(cache_key)

        if ptkp_amount is not None:
            return ptkp_amount

        # Check if PPh 21 Settings exists
        if not pph_settings and frappe.db.exists("DocType", "PPh 21 Settings"):
            try:
                pph_settings = frappe.get_cached_doc("PPh 21 Settings")
            except Exception as e:
                log_tax_logic_error("Settings Error", f"Error getting PPh 21 Settings: {str(e)}")

        # Get PTKP from settings
        ptkp_table = []
        if pph_settings and hasattr(pph_settings, "ptkp_table"):
            ptkp_table = pph_settings.ptkp_table

        # If not found in cached doc, query from database
        if not ptkp_table and pph_settings:
            try:
                ptkp_table = frappe.db.sql(
                    """
                    SELECT status_pajak as tax_status, ptkp_amount as amount
                    FROM `tabPPh 21 PTKP Table`
                    WHERE parent = 'PPh 21 Settings'
                """,
                    as_dict=1,
                )
            except Exception as e:
                log_tax_logic_error("Database Error", f"Error querying PTKP table: {str(e)}")

        # Find matching status with safe attribute access
        for ptkp in ptkp_table:
            # Check for tax_status field
            if hasattr(ptkp, "tax_status") and getattr(ptkp, "tax_status", "") == status_pajak:
                ptkp_amount = flt(getattr(ptkp, "amount", 0))
                if ptkp_amount > 0:
                    cache_value(cache_key, ptkp_amount, CACHE_LONG)
                    return ptkp_amount

            # For backward compatibility, check status_pajak field
            if hasattr(ptkp, "status_pajak") and getattr(ptkp, "status_pajak", "") == status_pajak:
                ptkp_amount = flt(getattr(ptkp, "ptkp_amount", 0))
                if ptkp_amount > 0:
                    cache_value(cache_key, ptkp_amount, CACHE_LONG)
                    return ptkp_amount

        # If not found, try to match prefix (TK0 -> TK) with safe string operations
        prefix = ""
        try:
            prefix = status_pajak[:2] if len(status_pajak) >= 2 else status_pajak
        except Exception:
            prefix = status_pajak

        if prefix:
            for ptkp in ptkp_table:
                ptkp_status = ""
                if hasattr(ptkp, "tax_status"):
                    ptkp_status = getattr(ptkp, "tax_status", "")
                elif hasattr(ptkp, "status_pajak"):
                    ptkp_status = getattr(ptkp, "status_pajak", "")

                if ptkp_status and ptkp_status.startswith(prefix):
                    # Get amount with appropriate field name based on object structure
                    if hasattr(ptkp, "amount"):
                        ptkp_amount = flt(getattr(ptkp, "amount", 0))
                    else:
                        ptkp_amount = flt(getattr(ptkp, "ptkp_amount", 0))

                    if ptkp_amount > 0:
                        cache_value(cache_key, ptkp_amount, CACHE_LONG)
                        return ptkp_amount

        # Default values if not found or settings don't exist - based on PMK-101/PMK.010/2016 and updated values
        default_ptkp = {"TK": 54000000, "K": 58500000, "HB": 112500000}  # TK/0  # K/0  # HB/0

        # Find default based on prefix with safe access
        for key, value in default_ptkp.items():
            try:
                if prefix.startswith(key):
                    log_tax_logic_error(
                        "PTKP Fallback",
                        f"PTKP not found in settings for {status_pajak}, using default value {value}",
                    )
                    cache_value(cache_key, value, CACHE_LONG)
                    return value
            except Exception:
                # If string operation fails, continue to next key
                continue

        # Last resort - TK0 default value
        default_value = 54000000  # Default for TK0
        log_tax_logic_error(
            "PTKP Default",
            f"No PTKP match found for {status_pajak}, using TK0 default ({default_value})",
        )
        cache_value(cache_key, default_value, CACHE_LONG)
        return default_value

    except Exception as e:
        # Non-critical error - log and return default
        log_tax_logic_error("PTKP Error", f"Error getting PTKP amount for {status_pajak}: {str(e)}")
        # Return default PTKP for TK0
        return 54000000


def should_use_ter_method(employee, slip=None):
    """
    Determine if TER method should be used for this employee according to PMK 168/2023
    Enhanced with better validation and error handling

    Args:
        employee: Employee document or dict
        slip: Salary slip document (optional)

    Returns:
        bool: True if TER should be used, False otherwise
    """
    try:
        # Validate employee parameter
        if not employee:
            return False

        # Employee can be dict or document - extract ID safely
        employee_id = "unknown"
        try:
            if hasattr(employee, "name"):
                employee_id = getattr(employee, "name", "unknown")
            elif isinstance(employee, dict):
                employee_id = employee.get("name", "unknown")
        except Exception:
            # If extraction fails, continue with default ID
            pass

        # Check cache first
        cache_key = f"use_ter:{employee_id}"
        cached_result = get_cached_value(cache_key)

        if cached_result is not None:
            return cached_result

        # Get PPh 21 Settings - use cached value for better performance
        settings_cache_key = "pph_settings:use_ter"
        pph_settings = get_cached_value(settings_cache_key)

        if pph_settings is None:
            try:
                pph_settings = (
                    frappe.get_cached_value(
                        "PPh 21 Settings",
                        "PPh 21 Settings",
                        ["calculation_method", "use_ter"],
                        as_dict=True,
                    )
                    or {}
                )
                # Cache settings for 1 hour
                cache_value(settings_cache_key, pph_settings, CACHE_MEDIUM)
            except Exception as e:
                log_tax_logic_error(
                    "Settings Error", f"Error retrieving PPh 21 Settings: {str(e)}"
                )
                pph_settings = {}

        # Fast path for global TER setting disabled - with default safety
        use_ter_setting = False
        calculation_method = ""

        # Extract settings safely
        if isinstance(pph_settings, dict):
            use_ter_setting = pph_settings.get("use_ter", False)
            calculation_method = pph_settings.get("calculation_method", "")
        else:
            # Try object access if it's not a dict
            use_ter_setting = getattr(pph_settings, "use_ter", False) if pph_settings else False
            calculation_method = (
                getattr(pph_settings, "calculation_method", "") if pph_settings else ""
            )

        # Check global settings
        if not use_ter_setting or calculation_method != "TER":
            cache_value(cache_key, False, CACHE_MEDIUM)  # Cache for 1 hour
            return False

        # Check for December override in salary slip
        if slip and getattr(slip, "is_december_override", 0):
            cache_value(cache_key, False, CACHE_MEDIUM)  # Cache for 1 hour
            return False

        # Extract employee attributes safely
        tipe_karyawan = ""
        override_tax_method = ""

        # Try to get attributes from employee with different access methods
        try:
            if hasattr(employee, "tipe_karyawan"):
                tipe_karyawan = getattr(employee, "tipe_karyawan", "")
            elif isinstance(employee, dict):
                tipe_karyawan = employee.get("tipe_karyawan", "")

            if hasattr(employee, "override_tax_method"):
                override_tax_method = getattr(employee, "override_tax_method", "")
            elif isinstance(employee, dict):
                override_tax_method = employee.get("override_tax_method", "")
        except Exception as e:
            log_tax_logic_error(
                "Attribute Access",
                f"Error accessing employee attributes: {str(e)}",
                {"employee_id": employee_id},
            )

        # Fast path for employee exclusions
        if tipe_karyawan == "Freelance":
            cache_value(cache_key, False, CACHE_MEDIUM)  # Cache for 1 hour
            return False

        if override_tax_method == "Progressive":
            cache_value(cache_key, False, CACHE_MEDIUM)  # Cache for 1 hour
            return False

        # If explicit override to TER
        if override_tax_method == "TER":
            cache_value(cache_key, True, CACHE_MEDIUM)  # Cache for 1 hour
            return True

        # If we made it here, use TER method
        cache_value(cache_key, True, CACHE_MEDIUM)  # Cache for 1 hour
        return True

    except Exception as e:
        # Log error but don't break functionality
        log_tax_logic_error(
            "TER Eligibility",
            f"Error determining TER eligibility: {str(e)}",
            {"employee_id": employee_id if "employee_id" in locals() else "unknown"},
        )
        # Default to False on error (use progressive method)
        return False


def hitung_pph_tahunan(employee, year, employee_details=None):
    """
    Calculate annual PPh 21 for an employee with support for both TER and progressive methods.
    Enhanced with better validation and error handling.

    Args:
        employee: Employee ID
        year: Tax year
        employee_details: Pre-fetched employee details (optional)

    Returns:
        dict: Tax calculation data
    """
    try:
        # Default return object for early returns or error cases
        default_result = {
            "annual_income": 0,
            "biaya_jabatan": 0,
            "bpjs_total": 0,
            "annual_net": 0,
            "ptkp": 0,
            "pkp": 0,
            "already_paid": 0,
            "annual_tax": 0,
            "ter_used": False,
            "ter_category": "",
        }

        # Validate parameters
        if not employee:
            log_tax_logic_error("Annual PPh", "Employee ID is required for annual PPh calculation")
            return default_result

        # Ensure year is valid
        valid_year = 0
        try:
            valid_year = int(year)
            if not (2000 <= valid_year <= 2100):  # Reasonable range check
                valid_year = getdate().year  # Default to current year
        except (ValueError, TypeError):
            valid_year = getdate().year  # Default to current year
            log_tax_logic_error(
                "Annual PPh", f"Invalid year provided: {year}, using current year {valid_year}"
            )

        # Get employee document if not provided
        emp_doc = employee_details or None
        if not emp_doc:
            try:
                emp_doc = frappe.get_doc("Employee", employee)
            except Exception as e:
                log_tax_logic_error(
                    "Employee Not Found", f"Error retrieving employee {employee}: {str(e)}"
                )
                return default_result

        # Get all salary slips for the year
        try:
            salary_slips = frappe.db.get_all(
                "Salary Slip",
                filters={
                    "employee": employee,
                    "docstatus": 1,
                    "start_date": ["between", [f"{valid_year}-01-01", f"{valid_year}-12-31"]],
                },
                fields=[
                    "name",
                    "gross_pay",
                    "total_bpjs",
                    "start_date",
                    "is_using_ter",
                    "ter_rate",
                    "ter_category",
                ],
                order_by="start_date asc",
            )
        except Exception as e:
            log_tax_logic_error(
                "Salary Slip Query",
                f"Error querying salary slips: {str(e)}",
                {"employee": employee, "year": valid_year},
            )
            salary_slips = []

        if not salary_slips:
            return default_result

        # Calculate annual totals safely
        annual_income = 0
        bpjs_total = 0

        for slip in salary_slips:
            # Safe access to values
            gross_pay = flt(getattr(slip, "gross_pay", 0))
            total_bpjs = flt(getattr(slip, "total_bpjs", 0))

            annual_income += gross_pay
            bpjs_total += total_bpjs

        # Calculate biaya jabatan (job allowance) with safety checks
        biaya_jabatan = 0
        if annual_income > 0:
            biaya_jabatan = min(annual_income * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX)

        # Calculate annual net income
        annual_net = annual_income - biaya_jabatan - bpjs_total

        # Get PTKP value based on employee's tax status
        status_pajak = "TK0"  # Default
        if emp_doc:
            # Try different ways to get status_pajak
            if hasattr(emp_doc, "status_pajak"):
                status_pajak = getattr(emp_doc, "status_pajak", "TK0") or "TK0"
            elif isinstance(emp_doc, dict):
                status_pajak = emp_doc.get("status_pajak", "TK0") or "TK0"

        # Get PTKP with our improved function
        ptkp = get_ptkp_amount(status_pajak)

        # Calculate PKP (taxable income)
        pkp = max(annual_net - ptkp, 0)

        # Check if TER was used in any month safely
        ter_used = False
        try:
            ter_used = any(
                cint(getattr(slip, "is_using_ter", 0)) > 0 or cint(slip.get("is_using_ter", 0)) > 0
                for slip in salary_slips
            )
        except Exception:
            # If access fails, assume TER wasn't used
            ter_used = False

        # Calculate tax paid during the year
        already_paid = calculate_tax_already_paid(salary_slips)

        # Calculate annual tax using progressive method
        try:
            annual_tax, _ = calculate_progressive_tax(pkp)
        except Exception as e:
            log_tax_logic_error(
                "Annual Tax", f"Error calculating annual tax: {str(e)}", {"pkp": pkp}
            )
            annual_tax = 0

        # Determine most common TER category if TER was used
        ter_categories = []
        ter_category = ""

        try:
            # Collect TER categories safely
            for slip in salary_slips:
                slip_ter_category = ""
                is_using_ter = False

                # Get is_using_ter safely
                try:
                    is_using_ter = (
                        cint(getattr(slip, "is_using_ter", 0)) > 0
                        or cint(slip.get("is_using_ter", 0)) > 0
                    )
                except Exception:
                    is_using_ter = False

                # Get ter_category safely
                try:
                    slip_ter_category = getattr(slip, "ter_category", "") or slip.get(
                        "ter_category", ""
                    )
                except Exception:
                    slip_ter_category = ""

                if is_using_ter and slip_ter_category:
                    ter_categories.append(slip_ter_category)

            # Find most common if we have categories
            if ter_categories:
                from collections import Counter

                category_counts = Counter(ter_categories)
                ter_category = category_counts.most_common(1)[0][0]
        except Exception as e:
            log_tax_logic_error("TER Category", f"Error determining TER category: {str(e)}")
            ter_category = ""

        # If TER wasn't used but we have status_pajak, determine TER category
        if not ter_category and status_pajak:
            try:
                ter_category = map_ptkp_to_ter_category(status_pajak)
            except Exception:
                # Use fallback value on error
                ter_category = "TER C"

        return {
            "annual_income": annual_income,
            "biaya_jabatan": biaya_jabatan,
            "bpjs_total": bpjs_total,
            "annual_net": annual_net,
            "ptkp": ptkp,
            "pkp": pkp,
            "already_paid": already_paid,
            "annual_tax": annual_tax,
            "ter_used": ter_used,
            "ter_category": ter_category,
        }

    except Exception as e:
        # Log error and return default values
        log_tax_logic_error(
            "Annual PPh Error",
            f"Error calculating annual PPh: {str(e)}",
            {"employee": employee, "year": year},
        )
        # Return empty result
        return {
            "annual_income": 0,
            "biaya_jabatan": 0,
            "bpjs_total": 0,
            "annual_net": 0,
            "ptkp": 0,
            "pkp": 0,
            "already_paid": 0,
            "annual_tax": 0,
            "ter_used": False,
            "ter_category": "",
        }


def calculate_tax_already_paid(salary_slips):
    """
    Calculate total tax already paid in the given salary slips
    Enhanced with better validation and error handling

    Args:
        salary_slips: List of salary slips

    Returns:
        float: Total tax already paid
    """
    # Initialize total
    total_tax = 0

    try:
        # Validate input
        if not salary_slips:
            return 0

        # Extract slip names safely
        slip_names = []
        for slip in salary_slips:
            try:
                if hasattr(slip, "name"):
                    slip_name = getattr(slip, "name")
                    if slip_name:
                        slip_names.append(slip_name)
                elif isinstance(slip, dict) and "name" in slip:
                    slip_name = slip["name"]
                    if slip_name:
                        slip_names.append(slip_name)
            except Exception:
                # Skip this slip on error
                continue

        if not slip_names:
            return 0

        # Get PPh 21 component amounts in bulk with error handling
        try:
            if len(slip_names) == 1:
                # Handle single slip case
                tax_components = frappe.db.sql(
                    """
                    SELECT parent, amount
                    FROM `tabSalary Detail`
                    WHERE
                        parent = %s
                        AND parentfield = 'deductions'
                        AND salary_component = 'PPh 21'
                """,
                    slip_names[0],
                    as_dict=1,
                )
            else:
                # Handle multiple slips case
                tax_components = frappe.db.sql(
                    """
                    SELECT parent, amount
                    FROM `tabSalary Detail`
                    WHERE
                        parent IN %s
                        AND parentfield = 'deductions'
                        AND salary_component = 'PPh 21'
                """,
                    [tuple(slip_names)],
                    as_dict=1,
                )
        except Exception as e:
            log_tax_logic_error(
                "Tax Components Query",
                f"Error querying tax components: {str(e)}",
                {"slip_names": slip_names},
            )
            return 0

        # Sum up tax amounts safely
        for comp in tax_components:
            try:
                total_tax += flt(comp.get("amount", 0))
            except Exception:
                # Skip this component on error
                continue

        return total_tax

    except Exception as e:
        # Log error and return 0
        log_tax_logic_error("Tax Already Paid", f"Error calculating already paid tax: {str(e)}")
        return 0


def detect_annual_income(gross_pay, total_earnings=0, basic_salary=0, bypass_detection=False):
    """
    Detect if a gross pay value appears to be annual rather than monthly
    Enhanced with better validation and safer calculations

    Args:
        gross_pay: The gross pay amount to check
        total_earnings: Sum of all earnings components (optional)
        basic_salary: Basic salary component amount (optional)
        bypass_detection: Flag to bypass detection logic

    Returns:
        tuple: (is_annual, reason, monthly_equivalent)
    """
    # Default return values
    is_annual = False
    reason = ""

    # Convert and validate all numeric inputs
    try:
        gross_pay_value = flt(gross_pay)
    except (ValueError, TypeError):
        log_tax_logic_error("Annual Detection", f"Invalid gross_pay value: {gross_pay}, using 0")
        gross_pay_value = 0

    try:
        total_earnings_value = flt(total_earnings)
    except (ValueError, TypeError):
        log_tax_logic_error(
            "Annual Detection", f"Invalid total_earnings value: {total_earnings}, using 0"
        )
        total_earnings_value = 0

    try:
        basic_salary_value = flt(basic_salary)
    except (ValueError, TypeError):
        log_tax_logic_error(
            "Annual Detection", f"Invalid basic_salary value: {basic_salary}, using 0"
        )
        basic_salary_value = 0

    # Default monthly value
    monthly_gross_pay = gross_pay_value

    # Early return if bypassing detection or gross_pay is zero/negative
    if bypass_detection or gross_pay_value <= 0:
        return False, "", gross_pay_value

    # Detection based on total earnings with validation
    if total_earnings_value > 0 and gross_pay_value > (
        total_earnings_value * ANNUAL_DETECTION_FACTOR
    ):
        is_annual = True
        reason = f"Gross pay ({gross_pay_value:,.0f}) exceeds {ANNUAL_DETECTION_FACTOR}x total earnings ({total_earnings_value:,.0f})"

        # Set monthly equivalent to total earnings if it's reasonable
        if total_earnings_value > 0 and total_earnings_value < gross_pay_value:
            monthly_gross_pay = total_earnings_value
        else:
            # Fallback to dividing by months per year
            monthly_gross_pay = gross_pay_value / MONTHS_PER_YEAR

    # Detection based on threshold value
    elif gross_pay_value > TAX_DETECTION_THRESHOLD:
        is_annual = True
        reason = f"Gross pay ({gross_pay_value:,.0f}) exceeds threshold {TAX_DETECTION_THRESHOLD:,.0f} (likely annual)"
        monthly_gross_pay = gross_pay_value / MONTHS_PER_YEAR

    # Detection based on basic salary ratio
    elif basic_salary_value > 0 and gross_pay_value > (basic_salary_value * SALARY_BASIC_FACTOR):
        is_annual = True
        reason = f"Gross pay ({gross_pay_value:,.0f}) exceeds {SALARY_BASIC_FACTOR}x basic salary ({basic_salary_value:,.0f})"

        # Check if it looks like exactly 12 months of basic salary
        ratio = gross_pay_value / basic_salary_value if basic_salary_value > 0 else 0
        if 11 < ratio < 13:
            # It's likely exactly 12 months, so divide by 12
            monthly_gross_pay = gross_pay_value / MONTHS_PER_YEAR
        else:
            # Otherwise use total earnings if it's reasonable
            if total_earnings_value > 0 and total_earnings_value < gross_pay_value:
                monthly_gross_pay = total_earnings_value
            else:
                # Fallback to dividing by months per year
                monthly_gross_pay = gross_pay_value / MONTHS_PER_YEAR

    # Ensure monthly_gross_pay is not negative or zero
    if monthly_gross_pay <= 0:
        monthly_gross_pay = gross_pay_value
        is_annual = False
        reason = "Detection failed to calculate valid monthly amount"
        log_tax_logic_error(
            "Annual Detection",
            "Detection produced invalid monthly amount, using original value",
            {"gross_pay": gross_pay_value, "monthly_calculated": monthly_gross_pay},
        )

    return is_annual, reason, monthly_gross_pay


def add_tax_info_to_note(doc, tax_method, values):
    """
    Add tax calculation details to payroll note with consistent formatting and
    section management to avoid duplication. Enhanced with better field validation.

    Args:
        doc: Salary slip document
        tax_method: "PROGRESSIVE", "TER", or "PROGRESSIVE_DECEMBER"
        values: Dictionary with calculation values
    """
    try:
        # Safely check if doc is valid
        if not doc:
            log_tax_logic_error("Tax Note", "Invalid document provided to add_tax_info_to_note")
            return

        # Safely check if payroll_note attribute exists and create if not
        if not hasattr(doc, "payroll_note") or doc.payroll_note is None:
            try:
                doc.payroll_note = ""
            except Exception:
                # If we can't set the attribute, we can't continue
                log_tax_logic_error("Tax Note", "Cannot set payroll_note attribute on document")
                return

        # Initialize note content
        note_content = [
            "\n\n<!-- TAX_CALCULATION_START -->",
        ]

        # Helper function for safe access to values
        def get_safe_value(key, default=0, format_fn=None):
            try:
                if isinstance(values, dict) and key in values:
                    value = values[key]
                    if format_fn:
                        return format_fn(value)
                    return value
                return default
            except Exception:
                return default

        # Helper function for formatting currencies
        def format_currency(value):
            try:
                return f"{flt(value):,.0f}"
            except Exception:
                return "0"

        # Helper function for formatting percentages
        def format_percent(value):
            try:
                return f"{flt(value):.2f}"
            except Exception:
                return "0.00"

        # Generate tax info based on method
        if tax_method == "TER":
            # TER method
            status_pajak = get_safe_value("status_pajak", "TK0")
            ter_category = get_safe_value("ter_category", "")
            mapping_info = f" → {ter_category}" if ter_category else ""
            gross_pay = get_safe_value("gross_pay", 0, format_currency)
            ter_rate = get_safe_value("ter_rate", 0, format_percent)
            monthly_tax = get_safe_value("monthly_tax", 0, format_currency)

            note_content.extend(
                [
                    "=== Perhitungan PPh 21 dengan TER ===",
                    f"Status Pajak: {status_pajak}{mapping_info}",
                    f"Penghasilan Bruto: Rp {gross_pay}",
                    f"Tarif Efektif Rata-rata: {ter_rate}%",
                    f"PPh 21 Sebulan: Rp {monthly_tax}",
                    "",
                    "Sesuai PMK 168/2023 tentang Tarif Efektif Rata-rata",
                ]
            )

        elif tax_method == "PROGRESSIVE_DECEMBER":
            # Progressive method for December
            status_pajak = get_safe_value("status_pajak", "TK0")
            annual_gross = get_safe_value("annual_gross", 0, format_currency)
            annual_biaya_jabatan = get_safe_value("annual_biaya_jabatan", 0, format_currency)
            annual_bpjs = get_safe_value("annual_bpjs", 0, format_currency)
            annual_netto = get_safe_value("annual_netto", 0, format_currency)
            ptkp = get_safe_value("ptkp", 0, format_currency)
            pkp = get_safe_value("pkp", 0, format_currency)

            note_content.extend(
                [
                    "=== Perhitungan PPh 21 Tahunan (Desember) ===",
                    f"Penghasilan Bruto Setahun: Rp {annual_gross}",
                    f"Biaya Jabatan: Rp {annual_biaya_jabatan}",
                    f"Total BPJS: Rp {annual_bpjs}",
                    f"Penghasilan Neto: Rp {annual_netto}",
                    f"PTKP ({status_pajak}): Rp {ptkp}",
                    f"PKP: Rp {pkp}",
                    "",
                    "Perhitungan Per Lapisan Pajak:",
                ]
            )

            # Add tax bracket details if available
            tax_details = get_safe_value("tax_details", [])
            if tax_details:
                for d in tax_details:
                    try:
                        rate = flt(d.get("rate", 0))
                        taxable = flt(d.get("taxable", 0))
                        tax = flt(d.get("tax", 0))
                        note_content.append(
                            f"- Lapisan {rate:.0f}%: "
                            f"Rp {taxable:,.0f} × {rate:.0f}% = "
                            f"Rp {tax:,.0f}"
                        )
                    except Exception:
                        # Skip this detail on error
                        continue
            else:
                note_content.append("- (Tidak ada rincian pajak)")

            # Add summary values
            annual_pph = get_safe_value("annual_pph", 0, format_currency)
            ytd_pph = get_safe_value("ytd_pph", 0, format_currency)
            correction = get_safe_value("correction", 0, format_currency)
            is_kurang_bayar = flt(get_safe_value("correction", 0)) > 0

            note_content.extend(
                [
                    "",
                    f"Total PPh 21 Setahun: Rp {annual_pph}",
                    f"PPh 21 Sudah Dibayar: Rp {ytd_pph}",
                    f"Koreksi Desember: Rp {correction}",
                    f"({'Kurang Bayar' if is_kurang_bayar else 'Lebih Bayar'})",
                    "",
                    "Metode perhitungan Desember menggunakan metode progresif sesuai PMK 168/2023",
                ]
            )

        elif tax_method == "PROGRESSIVE":
            # Regular progressive method
            status_pajak = get_safe_value("status_pajak", "TK0")
            monthly_netto = get_safe_value("monthly_netto", 0, format_currency)
            annual_netto = get_safe_value("annual_netto", 0, format_currency)
            ptkp = get_safe_value("ptkp", 0, format_currency)
            pkp = get_safe_value("pkp", 0, format_currency)

            note_content.extend(
                [
                    "=== Perhitungan PPh 21 dengan Metode Progresif ===",
                    f"Status Pajak: {status_pajak}",
                    f"Penghasilan Neto Sebulan: Rp {monthly_netto}",
                    f"Penghasilan Neto Setahun: Rp {annual_netto}",
                    f"PTKP: Rp {ptkp}",
                    f"PKP: Rp {pkp}",
                    "",
                    "PPh 21 Tahunan:",
                ]
            )

            # Add tax bracket details if available
            tax_details = get_safe_value("tax_details", [])
            if tax_details:
                for d in tax_details:
                    try:
                        rate = flt(d.get("rate", 0))
                        taxable = flt(d.get("taxable", 0))
                        tax = flt(d.get("tax", 0))
                        note_content.append(
                            f"- Lapisan {rate:.0f}%: "
                            f"Rp {taxable:,.0f} × {rate:.0f}% = "
                            f"Rp {tax:,.0f}"
                        )
                    except Exception:
                        # Skip this detail on error
                        continue
            else:
                note_content.append("- (Tidak ada rincian pajak)")

            # Add monthly PPh
            annual_pph = get_safe_value("annual_pph", 0, format_currency)
            monthly_pph = get_safe_value("monthly_pph", 0, format_currency)

            note_content.extend(
                [
                    "",
                    f"Total PPh 21 Setahun: Rp {annual_pph}",
                    f"PPh 21 Sebulan: Rp {monthly_pph}",
                ]
            )

        else:
            # Simple message (e.g., for NPWP Gabung Suami case)
            message = get_safe_value("message", "")
            if message:
                note_content.extend(["=== Informasi Pajak ===", message])
            else:
                note_content.extend(
                    ["=== Informasi Pajak ===", "Tidak ada perhitungan PPh 21 yang dilakukan."]
                )

        # Add end marker
        note_content.append("<!-- TAX_CALCULATION_END -->")

        # Check if we need to handle existing tax calculation section
        current_note = getattr(doc, "payroll_note", "") or ""

        if (
            "<!-- TAX_CALCULATION_START -->" in current_note
            and "<!-- TAX_CALCULATION_END -->" in current_note
        ):
            # Find and remove the existing section
            try:
                start_idx = current_note.find("<!-- TAX_CALCULATION_START -->")
                end_idx = current_note.find("<!-- TAX_CALCULATION_END -->") + len(
                    "<!-- TAX_CALCULATION_END -->"
                )

                if start_idx >= 0 and end_idx > start_idx:
                    # Remove existing section and replace with new one
                    doc.payroll_note = (
                        current_note[:start_idx] + "\n".join(note_content) + current_note[end_idx:]
                    )
                else:
                    # Just append if indices are wrong
                    doc.payroll_note = current_note + "\n" + "\n".join(note_content)
            except Exception:
                # On error, just append
                doc.payroll_note = current_note + "\n" + "\n".join(note_content)
        else:
            # Just append if no existing section
            doc.payroll_note = current_note + "\n" + "\n".join(note_content)

        # Try to persist changes
        try:
            doc.db_set("payroll_note", doc.payroll_note, update_modified=False)
        except Exception:
            # If db_set fails, we've still updated the in-memory value
            pass

    except Exception as e:
        # Log error but don't break the process
        log_tax_logic_error("Note Error", f"Error adding tax info to note: {str(e)}")

        # Try to add a simple note
        try:
            if hasattr(doc, "payroll_note"):
                doc.payroll_note += "\n\nWarning: Could not add detailed tax calculation notes."
        except Exception:
            # Silently fail if even this fails
            pass
