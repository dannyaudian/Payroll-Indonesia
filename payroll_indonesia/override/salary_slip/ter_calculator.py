# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-20 09:05:49 by dannyaudian

"""
TER (Tarif Efektif Rata-rata) Calculator for Indonesian Payroll.

This module provides the core functionality for calculating PPh 21 tax using
the TER method as specified by PMK 168/PMK.010/2023. It relies on the centralized
functions for TER category mapping and rate retrieval.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

import frappe
from frappe import _
from frappe.utils import flt, getdate

from .base import update_component_amount

# Import cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value

# Import constants
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR,
    CACHE_LONG,
    CACHE_MEDIUM,
    TER_CATEGORY_C,
    TER_CATEGORIES,
)

# Import centralized TER function APIs from pph_ter module
from payroll_indonesia.payroll_indonesia.tax.pph_ter import (
    get_ter_rate,
    map_ptkp_to_ter_category,
)

# Import tax utilities for note generation and annual detection
from payroll_indonesia.payroll_indonesia.tax.ter_logic import (
    detect_annual_income,
    add_tax_info_to_note,
)

__all__ = ["calculate_monthly_pph_with_ter"]

# Initialize logger
logger = frappe.logger("Payroll Indonesia - TER")

# Default values for required fields
TER_REQUIRED_FIELDS = {
    "monthly_gross_for_ter": 0,
    "annual_taxable_income": 0,
    "ter_rate": 0,
    "ter_category": "",
    "is_using_ter": 0,
    "payroll_note": "",
}


@dataclass
class TerCalculationContext:
    """Context data for TER calculations to enhance logging and debugging."""

    employee_id: str
    employee_name: str
    status_pajak: str
    ter_category: str
    gross_income: float
    ter_rate: float
    tax_amount: float
    document_name: str = ""
    error_details: str = ""


def log_ter_error(
    error_type: str, message: str, doc=None, employee=None, context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Enhanced error logging for TER calculations.

    Args:
        error_type: Type of error (e.g., "Calculation", "Validation", "Mapping")
        message: The error message
        doc: Salary slip document (optional)
        employee: Employee document (optional)
        context: Additional context data (optional)

    Returns:
        str: Error log ID
    """
    try:
        # Extract key information
        doc_name = getattr(doc, "name", "unknown") if doc else "unknown"
        emp_name = getattr(employee, "name", "unknown") if employee else "unknown"

        # Create concise title
        title = f"TER {error_type}: {emp_name}"

        # Sanitize message to avoid nesting
        import re

        sanitized_message = message
        if "Error Log" in sanitized_message:
            sanitized_message = re.sub(r"Error Log [a-z0-9]+:", "", sanitized_message)
            sanitized_message = re.sub(r"\([^)]*Error Log [^)]*\)", "", sanitized_message)

        # Create clean message with context
        log_message = [
            f"Document: {doc_name}",
            f"Employee: {emp_name}",
            f"Details: {sanitized_message}",
        ]

        # Add context if provided
        if context:
            context_str = "\nContext:\n" + "\n".join(f"  {k}: {v}" for k, v in context.items())
            log_message.append(context_str)

        # Log to frappe error log
        log_id = frappe.log_error(message="\n\n".join(log_message), title=title)

        # Also log to structured logger for better integration with logging systems
        logger.error(
            f"{error_type}: {sanitized_message}",
            extra={
                "document": doc_name,
                "employee": emp_name,
                "error_type": error_type,
                "log_id": log_id,
            },
        )

        return log_id
    except Exception:
        # Fallback to basic logging
        try:
            return frappe.log_error(message=str(message), title="TER Error")
        except Exception:
            # Last resort - fail silently
            return ""


def ensure_ter_fields(doc) -> bool:
    """
    Ensure all required fields for TER calculation exist in the document.

    Args:
        doc: Salary slip document

    Returns:
        bool: True if all fields were initialized successfully
    """
    if not doc:
        return False

    try:
        for field, default_value in TER_REQUIRED_FIELDS.items():
            if not hasattr(doc, field) or getattr(doc, field) is None:
                setattr(doc, field, default_value)
                try:
                    # Persist to database if possible
                    doc.db_set(field, default_value, update_modified=False)
                except Exception:
                    # Continue if db_set fails - we already set in-memory value
                    pass
        return True
    except Exception as e:
        log_ter_error("Field Initialization", str(e), doc)
        return False


def calculate_monthly_pph_with_ter(doc: Any, employee: Any) -> bool:
    """
    Calculate monthly PPh 21 tax using TER method based on PMK 168/2023.

    This implementation uses the centralized TER rate functions from pph_ter module
    to ensure consistent tax calculations throughout the application.

    Args:
        doc: Salary slip document
        employee: Employee document

    Returns:
        bool: True if calculation was successful

    Raises:
        frappe.ValidationError: If calculation fails critically
    """
    try:
        # Ensure all required fields exist and are initialized
        ensure_ter_fields(doc)

        # Store original values for verification, with safe getattr access
        original_values = {
            "gross_pay": flt(getattr(doc, "gross_pay", 0)),
            "monthly_gross_for_ter": flt(getattr(doc, "monthly_gross_for_ter", 0)),
            "annual_taxable_income": flt(getattr(doc, "annual_taxable_income", 0)),
            "ter_rate": flt(getattr(doc, "ter_rate", 0)),
            "ter_category": getattr(doc, "ter_category", "") or "",
        }

        # Add concise log entry for debugging
        doc_name = getattr(doc, "name", "unknown")
        log_ter_error("Calculation Start", f"Beginning calculation for {doc_name}", doc, employee)

        # Validate employee status_pajak with safe access
        employee_status_pajak = getattr(employee, "status_pajak", "") if employee else ""
        if not employee_status_pajak:
            employee_status_pajak = "TK0"  # Default to TK0
            if hasattr(employee, "status_pajak"):
                employee.status_pajak = employee_status_pajak
            frappe.msgprint(
                _("Warning: Employee tax status not set, using TK0 as default"), indicator="orange"
            )

        # Start with gross pay as monthly income with safe access
        monthly_gross_pay = flt(getattr(doc, "gross_pay", 0))

        # Calculate total earnings safely
        total_earnings = 0
        if hasattr(doc, "earnings") and doc.earnings:
            try:
                total_earnings = sum(flt(getattr(e, "amount", 0)) for e in doc.earnings)
            except Exception:
                # If earnings calculation fails, use 0
                pass

        # Get basic salary safely
        basic_salary = 0
        if hasattr(doc, "earnings") and doc.earnings:
            try:
                basic_salary_list = [
                    flt(getattr(e, "amount", 0))
                    for e in doc.earnings
                    if getattr(e, "salary_component", "")
                    in ["Gaji Pokok", "Basic Salary", "Basic Pay"]
                ]
                basic_salary = basic_salary_list[0] if basic_salary_list else 0
            except Exception:
                # If basic salary calculation fails, use 0
                pass

        # Use centralized logic to detect annual income
        bypass_detection = bool(getattr(doc, "bypass_annual_detection", False))
        is_annual, reason, monthly_gross_pay = detect_annual_income(
            monthly_gross_pay, total_earnings, basic_salary, bypass_detection
        )

        # Log annual value detection
        if is_annual:
            log_message = f"Detected annual value: {reason}. Adjusted from {getattr(doc, 'gross_pay', 0)} to {monthly_gross_pay}"
            log_ter_error("Annual Value", log_message, doc)

            # Add to payroll note if the field exists
            if hasattr(doc, "payroll_note") and doc.payroll_note is not None:
                doc.payroll_note += f"\n[TER] {reason}. Using monthly value: {monthly_gross_pay}"

        # Set and save monthly and annual values safely
        annual_taxable_income = flt(monthly_gross_pay * MONTHS_PER_YEAR)

        # Save monthly_gross_for_ter with safety checks
        doc.monthly_gross_for_ter = monthly_gross_pay
        try:
            doc.db_set("monthly_gross_for_ter", monthly_gross_pay, update_modified=False)
        except Exception as e:
            log_ter_error("Field Update", f"Could not save monthly_gross_for_ter: {str(e)}", doc)

        # Save annual_taxable_income with safety checks
        doc.annual_taxable_income = annual_taxable_income
        try:
            doc.db_set("annual_taxable_income", annual_taxable_income, update_modified=False)
        except Exception as e:
            log_ter_error("Field Update", f"Could not save annual_taxable_income: {str(e)}", doc)

        # Determine TER category using centralized mapping function
        ter_category = ""
        try:
            # Use cache to avoid redundant mapping operations
            cache_key = f"ter_category:{employee_status_pajak}"
            ter_category = get_cached_value(cache_key)

            if ter_category is None:
                # Use centralized mapping function from pph_ter module
                ter_category = map_ptkp_to_ter_category(employee_status_pajak)
                if ter_category:
                    cache_value(cache_key, ter_category, CACHE_LONG)
                else:
                    # Fallback if mapping returns empty
                    ter_category = TER_CATEGORY_C  # Default to highest category
        except Exception as e:
            log_ter_error("Category Mapping", str(e), doc, employee)
            ter_category = TER_CATEGORY_C  # Default to highest category on error
            frappe.msgprint(
                _("Warning: Error mapping TER category, using TER C as default"), indicator="orange"
            )

        # Calculate monthly tax with improved error handling
        monthly_tax = 0
        ter_rate = 0

        try:
            # Get TER rate from centralized function
            ter_rate = get_ter_rate(ter_category, monthly_gross_pay)
            # Calculate tax amount
            monthly_tax = flt(monthly_gross_pay * ter_rate)

            # Round according to Indonesian tax rules (banker's rounding, 2 decimal places)
            context = decimal.getcontext().copy()
            context.rounding = decimal.ROUND_HALF_EVEN
            decimal.setcontext(context)
            monthly_tax = float(decimal.Decimal(str(monthly_tax)).quantize(decimal.Decimal("0.01")))

            # Create calculation context for logging
            calc_context = {
                "employee_id": getattr(employee, "name", "unknown"),
                "employee_name": getattr(employee, "employee_name", "Unknown Employee"),
                "status_pajak": employee_status_pajak,
                "ter_category": ter_category,
                "income": monthly_gross_pay,
                "ter_rate": ter_rate,
                "tax": monthly_tax,
            }

            # Log successful calculation
            logger.info(
                f"TER calculation successful for {calc_context['employee_name']} "
                f"({ter_category}, rate: {ter_rate:.5f}, tax: {monthly_tax})",
                extra=calc_context,
            )

        except Exception as e:
            # Log the error in detail
            log_ter_error(
                "Tax Calculation",
                f"Tax calculation failed: {str(e)}",
                doc,
                employee,
                {"ter_category": ter_category, "monthly_gross_pay": monthly_gross_pay},
            )

            # Fallback calculation using conservative approach
            try:
                # Use default rates as fallback
                default_rates = {
                    "TER A": 0.05,  # 5%
                    "TER B": 0.15,  # 15%
                    "TER C": 0.25,  # 25%
                }
                ter_rate = default_rates.get(ter_category, 0.25)  # Default to highest rate
                monthly_tax = flt(monthly_gross_pay * ter_rate)

                frappe.msgprint(
                    _("Warning: Using fallback TER rate {0}% due to calculation error.").format(
                        ter_rate * 100
                    ),
                    indicator="orange",
                )
            except Exception as e2:
                # Last resort fallback
                log_ter_error(
                    "Tax Calculation", f"Fallback calculation also failed: {str(e2)}", doc
                )
                ter_rate = 0.05  # Default to 5% as absolute fallback
                monthly_tax = flt(monthly_gross_pay * ter_rate)
                frappe.msgprint(
                    _("Warning: TER calculation failed, using default 5% tax rate"), indicator="red"
                )

        # Set and save TER info safely
        doc.is_using_ter = 1
        doc.ter_rate = flt(ter_rate * 100)  # Store as percentage
        doc.ter_category = ter_category

        # Save TER info to database with error handling
        try:
            doc.db_set("is_using_ter", 1, update_modified=False)
            doc.db_set("ter_rate", flt(ter_rate * 100), update_modified=False)
            doc.db_set("ter_category", ter_category, update_modified=False)
        except Exception as e:
            log_ter_error("Database Update", f"Could not save TER fields: {str(e)}", doc)

        # Update PPh 21 component with error handling
        try:
            update_component_amount(doc, "PPh 21", monthly_tax, "deductions")
        except Exception as e:
            log_ter_error("Component Update", f"Could not update PPh 21 component: {str(e)}", doc)
            frappe.msgprint(_("Warning: Could not update PPh 21 salary component"), indicator="red")

        # Add tax info to note with error handling
        try:
            add_tax_info_to_note(
                doc,
                "TER",
                {
                    "status_pajak": employee_status_pajak,
                    "ter_category": ter_category,
                    "gross_pay": monthly_gross_pay,
                    "ter_rate": ter_rate * 100,
                    "monthly_tax": monthly_tax,
                },
            )
        except Exception as e:
            log_ter_error("Tax Note", f"Could not add tax info to note: {str(e)}", doc)
            # Create minimal note if add_tax_info_to_note fails
            if hasattr(doc, "payroll_note"):
                doc.payroll_note += f"\nTER calculation: Rate {ter_rate * 100}%, Tax: {monthly_tax}"

        # Verify calculation integrity with safe access
        verify_calculation_integrity(
            doc=doc,
            original_values=original_values,
            monthly_gross_pay=monthly_gross_pay,
            annual_taxable_income=annual_taxable_income,
            ter_rate=ter_rate,
            ter_category=ter_category,
            monthly_tax=monthly_tax,
        )

        log_ter_error("Calculation Complete", f"Successfully calculated TER for {doc_name}", doc)
        return True

    except Exception as e:
        # Improved error logging that avoids nested errors
        log_ter_error("Calculation Failure", str(e), doc, employee)
        # Simplified error message to avoid nested errors
        frappe.throw(_("Failed to calculate PPh 21 using TER method. See error log for details."))


def normalize_ter_category(category: str) -> str:
    """
    Normalize TER category to ensure it uses the correct format.

    Args:
        category: TER category input (could be 'A', 'B', 'C', or 'TER A', etc.)

    Returns:
        Normalized TER category ('TER A', 'TER B', or 'TER C')
    """
    category = (category or "").strip().upper()

    # Convert single letter format to TER format
    if category in ["A", "B", "C"]:
        category = f"TER {category}"
    # Ensure category starts with "TER " prefix
    elif not category.startswith("TER "):
        category = TER_CATEGORY_C  # Default to highest category

    # Validate against allowed categories
    if category not in TER_CATEGORIES:
        category = TER_CATEGORY_C  # Default to highest category if invalid

    return category


def calculate_simple_pph_with_ter(
    employee: Union[str, Any],
    taxable_income: Union[float, int, str],
    ter_category: Optional[str] = None,
    status_pajak: Optional[str] = None,
) -> float:
    """
    Simplified version of PPh 21 calculation with TER for external usage.

    This function provides a straightforward API for calculating tax with TER
    without requiring a full salary slip document.

    Args:
        employee: Employee document or ID
        taxable_income: Monthly taxable income
        ter_category: TER category ('A', 'B', 'C', 'TER A', 'TER B', 'TER C')
        status_pajak: Tax status code (e.g., 'TK0', 'K1')

    Returns:
        float: Calculated monthly PPh 21 amount

    Example:
        >>> calculate_simple_pph_with_ter("EMP0001", 10000000, "TER B")
        1500000.0
    """
    # Extract employee ID if document provided
    employee_id = employee
    if hasattr(employee, "name"):
        employee_id = employee.name

    # Ensure taxable_income is a number
    try:
        income_value = flt(taxable_income)
    except (ValueError, TypeError):
        frappe.throw(_("Taxable income must be a valid number"))

    # If no ter_category provided but status_pajak is available, map it
    if not ter_category and status_pajak:
        try:
            # Extract status_pajak from employee if provided
            if not status_pajak and hasattr(employee, "status_pajak"):
                status_pajak = employee.status_pajak

            if status_pajak:
                ter_category = map_ptkp_to_ter_category(status_pajak)
        except Exception as e:
            frappe.log_error(
                f"Error mapping PTKP status {status_pajak} to TER category: {str(e)}",
                "TER Calculation Error",
            )

    # Normalize and validate the category
    category = normalize_ter_category(ter_category or "TER C")

    # Get the TER rate using centralized function
    rate = get_ter_rate(category, income_value)

    # Calculate tax with Indonesian rounding rules
    tax_amount = flt(income_value * rate)

    # Log the calculation
    logger.debug(
        f"Simple TER calculation: {income_value} × {rate} = {tax_amount}",
        extra={
            "employee": employee_id,
            "income": income_value,
            "category": category,
            "rate": rate,
            "tax": tax_amount,
        },
    )

    return tax_amount


def verify_calculation_integrity(
    doc: Any,
    original_values: Dict[str, Any],
    monthly_gross_pay: float,
    annual_taxable_income: float,
    ter_rate: float,
    ter_category: str,
    monthly_tax: float,
) -> bool:
    """
    Verify integrity of TER calculation results and fix any inconsistencies.

    This ensures all values are consistent with the calculation and properly saved.

    Args:
        doc: Salary slip document
        original_values: Dict of original values before calculation
        monthly_gross_pay: Calculated monthly gross pay
        annual_taxable_income: Calculated annual taxable amount
        ter_rate: Calculated TER rate (decimal)
        ter_category: Determined TER category
        monthly_tax: Calculated monthly tax amount

    Returns:
        bool: True if integrity is verified or issues were fixed

    Raises:
        frappe.ValidationError: If verification fails and cannot be fixed
    """
    if not doc:
        return False

    try:
        errors = []

        # Ensure critical fields exist before checking them
        ensure_ter_fields(doc)

        # Only verify gross_pay if it exists in both doc and original_values
        if hasattr(doc, "gross_pay") and "gross_pay" in original_values:
            if abs(flt(doc.gross_pay) - flt(original_values.get("gross_pay", 0))) > 0.01:
                errors.append(
                    f"gross_pay changed: {original_values.get('gross_pay', 0)} → {doc.gross_pay}"
                )
                doc.gross_pay = flt(original_values.get("gross_pay", 0))
                try:
                    doc.db_set(
                        "gross_pay", flt(original_values.get("gross_pay", 0)), update_modified=False
                    )
                except Exception:
                    # Continue if db_set fails
                    pass

        # Verify monthly_gross_for_ter
        if hasattr(doc, "monthly_gross_for_ter"):
            # Only do comparison if values actually differ significantly
            if abs(flt(doc.monthly_gross_for_ter) - flt(monthly_gross_pay)) > 0.01:
                errors.append(
                    f"monthly_gross_for_ter mismatch: expected {monthly_gross_pay}, "
                    f"got {doc.monthly_gross_for_ter}"
                )
                doc.monthly_gross_for_ter = flt(monthly_gross_pay)
                try:
                    doc.db_set(
                        "monthly_gross_for_ter", flt(monthly_gross_pay), update_modified=False
                    )
                except Exception:
                    # Continue if db_set fails
                    pass

        # Verify annual_taxable_income
        if hasattr(doc, "annual_taxable_income"):
            expected_annual = flt(monthly_gross_pay * MONTHS_PER_YEAR)
            if abs(flt(doc.annual_taxable_income) - expected_annual) > 0.01:
                errors.append(
                    f"annual_taxable_income mismatch: expected {expected_annual}, "
                    f"got {doc.annual_taxable_income}"
                )
                doc.annual_taxable_income = expected_annual
                try:
                    doc.db_set("annual_taxable_income", expected_annual, update_modified=False)
                except Exception:
                    # Continue if db_set fails
                    pass

        # Verify TER values
        if hasattr(doc, "is_using_ter") and not doc.is_using_ter:
            errors.append("is_using_ter not set to 1")
            doc.is_using_ter = 1
            try:
                doc.db_set("is_using_ter", 1, update_modified=False)
            except Exception:
                # Continue if db_set fails
                pass

        if hasattr(doc, "ter_rate"):
            if abs(flt(doc.ter_rate) - flt(ter_rate * 100)) > 0.01:
                errors.append(f"ter_rate mismatch: expected {ter_rate * 100}, got {doc.ter_rate}")
                doc.ter_rate = flt(ter_rate * 100)
                try:
                    doc.db_set("ter_rate", flt(ter_rate * 100), update_modified=False)
                except Exception:
                    # Continue if db_set fails
                    pass

        if hasattr(doc, "ter_category") and doc.ter_category != ter_category:
            errors.append(f"ter_category mismatch: expected {ter_category}, got {doc.ter_category}")
            doc.ter_category = ter_category
            try:
                doc.db_set("ter_category", ter_category, update_modified=False)
            except Exception:
                # Continue if db_set fails
                pass

        # Log all errors found in a clean format
        if errors:
            error_list = "\n".join(f"- {err}" for err in errors)
            log_ter_error("Integrity Check", f"Issues found and fixed:\n{error_list}", doc)

            # Add minimal message to user
            frappe.msgprint(
                _("Some TER calculation values were automatically corrected."),
                indicator="orange",
            )

            # Add to payroll_note if available
            if hasattr(doc, "payroll_note") and doc.payroll_note is not None:
                doc.payroll_note += "\n[TER] Fixed calculation issues:\n" + "\n".join(
                    f"- {err}" for err in errors
                )

        return True  # Return true even with errors since we fixed them

    except Exception as e:
        # Non-critical error - log but continue
        log_ter_error("Integrity Check", f"Verification failed: {str(e)}", doc)
        # Don't throw as this is a non-critical function
        return False


# YTD functions - to be moved to utils.py in a future refactoring
def get_ytd_totals_from_tax_summary(
    doc: Any, year: int, month: Optional[int] = None
) -> Dict[str, float]:
    """
    Get YTD tax totals from Employee Tax Summary.

    Args:
        doc: Salary slip document or employee ID string
        year: Tax year
        month: Month number (1-12), defaults to current month if not provided

    Returns:
        dict: YTD values (gross, tax, bpjs)
    """
    # Extract employee ID safely
    employee = None
    if isinstance(doc, str):
        employee = doc  # Already an employee ID
    elif hasattr(doc, "employee"):
        employee = doc.employee
    else:
        # Return empty result if no employee identified
        return {"gross": 0, "bpjs": 0, "pph21": 0}

    # Validate year
    if not year:
        # Try to get year from document
        if hasattr(doc, "start_date"):
            try:
                year = getdate(doc.start_date).year
            except Exception:
                # If parsing fails, use current year
                year = getdate().year
        else:
            year = getdate().year

    # Validate month
    if not month:
        # Try to get month from document
        if hasattr(doc, "start_date"):
            try:
                month = getdate(doc.start_date).month
            except Exception:
                # If parsing fails, use current month
                month = getdate().month
        else:
            month = getdate().month

    # Create cache key
    cache_key = f"ytd:{employee}:{year}:{month}"

    # Check cache first
    cached_result = get_cached_value(cache_key)
    if cached_result is not None:
        # Add fallback for YTD gross and BPJS if missing
        if "gross" not in cached_result and hasattr(doc, "ytd_gross_pay"):
            cached_result["gross"] = flt(doc.ytd_gross_pay)
        if "bpjs" not in cached_result and hasattr(doc, "ytd_bpjs_deductions"):
            cached_result["bpjs"] = flt(doc.ytd_bpjs_deductions)
        return cached_result

    try:
        # Use a parameterized query to get all needed data
        ytd_data = frappe.db.sql(
            """
            SELECT
                ETS.ytd_tax,
                SUM(ETSD.gross_pay) as ytd_gross,
                SUM(ETSD.bpjs_deductions) as ytd_bpjs
            FROM
                `tabEmployee Tax Summary` ETS
            LEFT JOIN
                `tabEmployee Tax Summary Detail` ETSD ON ETS.name = ETSD.parent
            WHERE
                ETS.employee = %s
                AND ETS.year = %s
                AND ETSD.month < %s
            GROUP BY
                ETS.name
            """,
            (employee, year, month),
            as_dict=1,
        )

        if ytd_data and len(ytd_data) > 0:
            result = {
                "gross": flt(ytd_data[0].ytd_gross),
                "pph21": flt(ytd_data[0].ytd_tax),
                "bpjs": flt(ytd_data[0].ytd_bpjs),
            }

            # Cache the result (for 1 hour)
            cache_value(cache_key, result, CACHE_MEDIUM)
            
            # Add fallback for YTD gross and BPJS if missing
            if "gross" not in result and hasattr(doc, "ytd_gross_pay"):
                result["gross"] = flt(doc.ytd_gross_pay)
            if "bpjs" not in result and hasattr(doc, "ytd_bpjs_deductions"):
                result["bpjs"] = flt(doc.ytd_bpjs_deductions)
                
            return result
        else:
            # No data found, return zeros
            result = {"gross": 0, "pph21": 0, "bpjs": 0}
            
            # Add fallback for YTD gross and BPJS if missing
            if "gross" not in result and hasattr(doc, "ytd_gross_pay"):
                result["gross"] = flt(doc.ytd_gross_pay)
            if "bpjs" not in result and hasattr(doc, "ytd_bpjs_deductions"):
                result["bpjs"] = flt(doc.ytd_bpjs_deductions)
                
            cache_value(cache_key, result, CACHE_MEDIUM)
            return result

    except Exception as e:
        # Log error and fall back to legacy method
        log_ter_error("YTD Data", f"Error getting YTD data: {str(e)}", doc)

        # Only show message to user if this is being called directly from UI
        if (
            frappe.local.form_dict.cmd
            == "payroll_indonesia.override.salary_slip.ter_calculator.get_ytd_totals_from_tax_summary"
        ):
            frappe.msgprint(
                _("Warning: Using fallback method to calculate YTD tax data"), indicator="orange"
            )

        # Fallback to the older method
        result = get_ytd_totals_from_tax_summary_legacy(employee, year, month)
        
        # Add fallback for YTD gross and BPJS if missing
        if "gross" not in result and hasattr(doc, "ytd_gross_pay"):
            result["gross"] = flt(doc.ytd_gross_pay)
        if "bpjs" not in result and hasattr(doc, "ytd_bpjs_deductions"):
            result["bpjs"] = flt(doc.ytd_bpjs_deductions)
            
        return result


def get_ytd_totals_from_tax_summary_legacy(
    employee: Union[str, Any], year: int, month: Optional[int] = None
) -> Dict[str, float]:
    """
    Legacy fallback method to get YTD tax totals from Employee Tax Summary.

    Args:
        employee: Employee ID or document
        year: Tax year
        month: Month number (1-12)

    Returns:
        dict: YTD values (gross, tax, bpjs)
    """
    # Standard default result
    default_result = {"gross": 0, "pph21": 0, "bpjs": 0}

    try:
        # Extract employee ID if needed
        if not isinstance(employee, str) and hasattr(employee, "name"):
            employee = employee.name

        # Validate parameters
        if not employee or not year:
            return default_result

        # Default month to current if not provided
        if not month:
            month = getdate().month

        # Find Employee Tax Summary for this employee and year
        tax_summary = frappe.get_all(
            "Employee Tax Summary",
            filters={"employee": employee, "year": year, "docstatus": ["!=", 2]},
            fields=["name", "ytd_tax"],
            limit=1,
        )

        if not tax_summary:
            return default_result

        # Get monthly details for YTD calculations
        monthly_details = frappe.get_all(
            "Employee Tax Summary Detail",
            filters={"parent": tax_summary[0].name, "month": ["<", month]},
            fields=["gross_pay", "bpjs_deductions"],
            order_by="month asc",
        )

        # Calculate YTD totals safely
        ytd_gross = sum(flt(getattr(d, "gross_pay", 0)) for d in monthly_details)
        ytd_bpjs = sum(flt(getattr(d, "bpjs_deductions", 0)) for d in monthly_details)
        ytd_tax = flt(tax_summary[0].ytd_tax)

        result = {"gross": ytd_gross, "pph21": ytd_tax, "bpjs": ytd_bpjs}

        # Cache the result
        cache_key = f"ytd:{employee}:{year}:{month}"
        cache_value(cache_key, result, CACHE_MEDIUM)

        return result

    except Exception as e:
        # Log error but return empty result
        log_ter_error("YTD Legacy", f"Failed to calculate YTD values: {str(e)}", None)
        return default_result
