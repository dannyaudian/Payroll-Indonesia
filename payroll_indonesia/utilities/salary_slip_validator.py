# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Created: 2025-05-23 04:28:09 by dannyaudian
# Last modified: 2025-06-17 07:28:35 by dannyaudian

from typing import Any, Dict, Optional, Union
import logging

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime


def get_logger() -> logging.Logger:
    """Get properly configured logger for salary slip validation module."""
    return frappe.logger("salary_slip_validator", with_more_info=True)


def debug_log(message: str, level: str = "debug") -> None:
    """
    Log a message with appropriate level and timestamp.

    Args:
        message: The message to log
        level: Log level (debug, info, warning, error)
    """
    logger = get_logger()
    timestamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{timestamp}] {message}"

    if level == "info":
        logger.info(formatted_message)
    elif level == "warning":
        logger.warning(formatted_message)
    elif level == "error":
        logger.error(formatted_message)
    else:
        logger.debug(formatted_message)


def get_salary_slip_with_validation(salary_slip: str) -> Optional[Any]:
    """
    Get and validate a Salary Slip document.

    Performs thorough validation to ensure the Salary Slip:
    - Exists
    - Has appropriate submission status
    - Contains all required fields

    Args:
        salary_slip: Name of the salary slip document

    Returns:
        The salary slip document if valid, None otherwise

    Example:
        >>> slip = get_salary_slip_with_validation("HR-SLP-2025-00001")
        >>> if slip:
        >>>     # Proceed with processing
        >>> else:
        >>>     # Handle invalid slip case
    """
    try:
        # Get the document
        debug_log(f"Retrieving salary slip: {salary_slip}")
        slip = frappe.get_doc("Salary Slip", salary_slip)

        # Validate document exists
        if not slip:
            debug_log(f"Salary slip {salary_slip} not found", "error")
            raise frappe.exceptions.DoesNotExistError(
                _("Salary Slip {0} not found").format(salary_slip)
            )

        # Validate document status
        if slip.docstatus != 1:
            debug_log(
                f"Salary slip {salary_slip} is not submitted (docstatus={slip.docstatus})",
                "warning",
            )
            raise frappe.exceptions.ValidationError(
                _("Salary Slip {0} must be submitted (current status: {1})").format(
                    salary_slip,
                    (
                        "Draft"
                        if slip.docstatus == 0
                        else "Cancelled" if slip.docstatus == 2 else "Unknown"
                    ),
                )
            )

        # Check required fields
        required_fields = ["employee", "start_date", "end_date"]
        for field in required_fields:
            if not hasattr(slip, field) or not getattr(slip, field):
                debug_log(f"Salary slip {salary_slip} missing required field: {field}", "warning")
                raise frappe.exceptions.ValidationError(
                    _("Salary Slip {0} is missing required field: {1}").format(salary_slip, field)
                )

        # Additional data validation
        if hasattr(slip, "gross_pay") and slip.gross_pay < 0:
            debug_log(
                f"Salary slip {salary_slip} has invalid negative gross pay: {slip.gross_pay}",
                "warning",
            )
            raise frappe.exceptions.ValidationError(
                _("Salary Slip {0} has invalid negative gross pay: {1}").format(
                    salary_slip, slip.gross_pay
                )
            )

        # Document is valid
        debug_log(f"Salary slip {salary_slip} passed validation")
        return slip

    except frappe.exceptions.DoesNotExistError as e:
        debug_log(f"Document not found error: {str(e)}", "error")
        return None

    except frappe.exceptions.ValidationError as e:
        debug_log(f"Validation error: {str(e)}", "warning")
        return None

    except Exception as e:
        debug_log(f"Unexpected error validating salary slip {salary_slip}: {str(e)}", "error")
        return None


def validate_tax_related_fields(slip: Any) -> Dict[str, Any]:
    """
    Validate tax-related fields in a Salary Slip.

    Args:
        slip: Salary Slip document

    Returns:
        Dictionary with validation results containing:
        - is_valid: Whether the slip is valid for tax processing
        - has_pph21: Whether the slip has PPh 21 component
        - error: Error message if validation failed
        - npwp: NPWP value if found
        - status_pajak: Tax status if found
    """
    result = {"is_valid": False, "has_pph21": False, "error": None, "npwp": "", "status_pajak": ""}

    try:
        if not slip:
            result["error"] = _("Invalid salary slip document")
            return result

        # Check if PPh 21 component exists
        if hasattr(slip, "deductions") and slip.deductions:
            for deduction in slip.deductions:
                if deduction.salary_component == "PPh 21" and flt(deduction.amount) > 0:
                    result["has_pph21"] = True
                    break

        # If no PPh 21 component, still valid but not tax-relevant
        if not result["has_pph21"]:
            result["is_valid"] = True
            return result

        # Get NPWP (Tax ID)
        if hasattr(slip, "npwp") and slip.npwp:
            result["npwp"] = slip.npwp
        elif hasattr(slip, "employee"):
            # Try to get from employee record
            result["npwp"] = frappe.db.get_value("Employee", slip.employee, "npwp") or ""

        # Get Tax Status
        if hasattr(slip, "employee"):
            result["status_pajak"] = (
                frappe.db.get_value("Employee", slip.employee, "status_pajak") or ""
            )

        # Validate NPWP
        if not result["npwp"]:
            result["error"] = _("NPWP (Tax ID) is required for PPh 21 calculation.")
            return result

        # Validate status_pajak
        if not result["status_pajak"]:
            result["error"] = _("Tax status (Status Pajak) is required for PPh 21 calculation.")
            return result

        # All checks passed
        result["is_valid"] = True
        return result

    except Exception as e:
        debug_log(f"Error validating tax fields: {str(e)}", "error")
        result["error"] = str(e)
        return result


def validate_salary_slip(doc: Any) -> Dict[str, Any]:
    """
    Comprehensive validation of a Salary Slip for tax and BPJS compliance.

    Args:
        doc: Salary Slip document

    Returns:
        Dictionary with validation results
    """
    result = {
        "is_valid": False,
        "messages": [],
        "warnings": [],
        "errors": [],
        "has_tax": False,
        "has_bpjs": False,
        "is_year_end": False,
    }

    try:
        if not doc or not isinstance(doc, object):
            result["errors"].append(_("Invalid salary slip document"))
            return result

        # Check if this is December or override is set (for year-end processing)
        result["is_year_end"] = bool(getattr(doc, "is_december_override", 0))

        # Check tax components
        # tax_amount = 0
        if hasattr(doc, "deductions") and doc.deductions:
            for deduction in doc.deductions:
                if deduction.salary_component == "PPh 21":
                    # tax_amount = flt(deduction.amount)
                    result["has_tax"] = True
                    break

        # Validate tax if present
        if result["has_tax"]:
            # Check employee tax fields
            if hasattr(doc, "employee"):
                npwp = frappe.db.get_value("Employee", doc.employee, "npwp")
                status_pajak = frappe.db.get_value("Employee", doc.employee, "status_pajak")

                if not npwp:
                    result["warnings"].append(_("Employee is missing NPWP (Tax ID)"))

                if not status_pajak:
                    result["warnings"].append(_("Employee is missing tax status (Status Pajak)"))

            # Check YTD tax for December/year-end
            if result["is_year_end"]:
                if not hasattr(doc, "ytd_tax") or flt(doc.ytd_tax) <= 0:
                    result["warnings"].append(_("Year-end salary slip should have YTD tax amount"))

        # Check BPJS components
        bpjs_components = ["BPJS Kesehatan Employee", "BPJS JHT Employee", "BPJS JP Employee"]
        found_bpjs = []

        if hasattr(doc, "deductions") and doc.deductions:
            for deduction in doc.deductions:
                if deduction.salary_component in bpjs_components and flt(deduction.amount) > 0:
                    found_bpjs.append(deduction.salary_component)

        result["has_bpjs"] = len(found_bpjs) > 0

        # If BPJS components are present, validate completeness
        if result["has_bpjs"]:
            # Check if all necessary components exist
            missing_components = [comp for comp in bpjs_components if comp not in found_bpjs]
            if missing_components:
                result["warnings"].append(
                    _("Some BPJS components are missing: {0}").format(", ".join(missing_components))
                )

            # Check BPJS employee registration
            if hasattr(doc, "employee"):
                ikut_bpjs = frappe.db.get_value(
                    "Employee", doc.employee, "ikut_bpjs_ketenagakerjaan"
                )
                if ikut_bpjs == 0:
                    result["warnings"].append(
                        _("Employee is not marked as BPJS participant but has BPJS deductions")
                    )

        # Final validation result
        if not result["errors"]:
            result["is_valid"] = True
            result["messages"].append(_("Salary slip passed validation"))

        return result

    except Exception as e:
        debug_log(f"Error in validate_salary_slip: {str(e)}", "error")
        result["errors"].append(str(e))
        return result


def validate_for_tax_summary(salary_slip: str) -> Dict[str, Any]:
    """
    Validate if a Salary Slip is suitable for tax summary processing.
    This combines document validation and tax field validation.

    Args:
        salary_slip: Name of the salary slip

    Returns:
        Dictionary with validation results containing:
        - is_valid: Overall validity for tax summary
        - slip: The salary slip document if valid
        - error: Error message if not valid
        - year: Tax year from the slip
        - month: Month number from the slip
        - has_pph21: Whether the slip has PPh 21 component
    """
    result = {
        "is_valid": False,
        "slip": None,
        "error": None,
        "year": None,
        "month": None,
        "has_pph21": False,
    }

    try:
        # Get and validate the document
        slip = get_salary_slip_with_validation(salary_slip)

        if not slip:
            result["error"] = _("Invalid or non-existent salary slip")
            return result

        # Store the document in result
        result["slip"] = slip

        # Get year and month
        if hasattr(slip, "end_date"):
            end_date = getdate(slip.end_date)
            result["year"] = end_date.year
            result["month"] = end_date.month
        else:
            result["error"] = _("Salary slip missing end date")
            return result

        # Validate tax fields
        tax_validation = validate_tax_related_fields(slip)
        result["has_pph21"] = tax_validation["has_pph21"]

        # If there are tax components, ensure tax fields are valid
        if result["has_pph21"] and not tax_validation["is_valid"]:
            result["error"] = tax_validation["error"]
            return result

        # All validations passed
        result["is_valid"] = True
        return result

    except Exception as e:
        debug_log(f"Error in validate_for_tax_summary: {str(e)}", "error")
        result["error"] = str(e)
        return result


def validate_for_bpjs_summary(salary_slip: str) -> Dict[str, Any]:
    """
    Validate if a Salary Slip is suitable for BPJS summary processing.

    Args:
        salary_slip: Name of the salary slip

    Returns:
        Dictionary with validation results containing:
        - is_valid: Overall validity for BPJS summary
        - slip: The salary slip document if valid
        - error: Error message if not valid
        - year: Year from the slip
        - month: Month number from the slip
        - has_bpjs: Whether the slip has BPJS components
    """
    result = {
        "is_valid": False,
        "slip": None,
        "error": None,
        "year": None,
        "month": None,
        "has_bpjs": False,
    }

    try:
        # Get and validate the document
        slip = get_salary_slip_with_validation(salary_slip)

        if not slip:
            result["error"] = _("Invalid or non-existent salary slip")
            return result

        # Store the document in result
        result["slip"] = slip

        # Get year and month
        if hasattr(slip, "end_date"):
            end_date = getdate(slip.end_date)
            result["year"] = end_date.year
            result["month"] = end_date.month
        else:
            result["error"] = _("Salary slip missing end date")
            return result

        # Check BPJS components
        bpjs_components = ["BPJS Kesehatan Employee", "BPJS JHT Employee", "BPJS JP Employee"]

        if hasattr(slip, "deductions") and slip.deductions:
            for deduction in slip.deductions:
                if deduction.salary_component in bpjs_components and flt(deduction.amount) > 0:
                    result["has_bpjs"] = True
                    break

        # All validations passed
        result["is_valid"] = True
        return result

    except Exception as e:
        debug_log(f"Error in validate_for_bpjs_summary: {str(e)}", "error")
        result["error"] = str(e)
        return result


def check_salary_slip_cancellation(salary_slip: str) -> Dict[str, Any]:
    """
    Check if a Salary Slip is properly cancelled for tax summary reversal.

    Args:
        salary_slip: Name of the salary slip

    Returns:
        Dictionary with check results containing:
        - is_cancelled: Whether the slip is properly cancelled
        - slip: The salary slip document if found
        - error: Error message if any issues
        - year: Tax year from the slip
        - month: Month number from the slip
    """
    result = {"is_cancelled": False, "slip": None, "error": None, "year": None, "month": None}

    try:
        # Attempt to get the salary slip
        try:
            slip = frappe.get_doc("Salary Slip", salary_slip)
            result["slip"] = slip
        except frappe.exceptions.DoesNotExistError:
            result["error"] = _("Salary Slip {0} not found").format(salary_slip)
            return result

        # Check document status
        if slip.docstatus != 2:  # 2 = Cancelled
            result["error"] = _("Salary Slip {0} is not cancelled (docstatus: {1})").format(
                salary_slip, slip.docstatus
            )
            return result

        # Extract date information
        if hasattr(slip, "end_date") and slip.end_date:
            end_date = getdate(slip.end_date)
            result["year"] = end_date.year
            result["month"] = end_date.month
        else:
            result["error"] = _("Cancelled salary slip missing end date")
            return result

        # All checks passed
        result["is_cancelled"] = True
        return result

    except Exception as e:
        debug_log(f"Error checking salary slip cancellation: {str(e)}", "error")
        result["error"] = str(e)
        return result


def has_pph21_component(salary_slip: Union[str, Any]) -> bool:
    """
    Check if a Salary Slip has PPh 21 tax component.

    Args:
        salary_slip: Salary Slip document or name

    Returns:
        True if the slip has PPh 21 component, False otherwise
    """
    try:
        # If string is passed, get the document
        if isinstance(salary_slip, str):
            slip = frappe.get_doc("Salary Slip", salary_slip)
        else:
            slip = salary_slip

        # Check deductions for PPh 21
        if hasattr(slip, "deductions") and slip.deductions:
            for deduction in slip.deductions:
                if deduction.salary_component == "PPh 21" and flt(deduction.amount) > 0:
                    return True

        return False

    except Exception as e:
        debug_log(f"Error checking for PPh 21 component: {str(e)}", "error")
        return False


def has_bpjs_components(salary_slip: Union[str, Any]) -> bool:
    """
    Check if a Salary Slip has any BPJS components.

    Args:
        salary_slip: Salary Slip document or name

    Returns:
        True if the slip has any BPJS components, False otherwise
    """
    try:
        # If string is passed, get the document
        if isinstance(salary_slip, str):
            slip = frappe.get_doc("Salary Slip", salary_slip)
        else:
            slip = salary_slip

        # BPJS component names to check
        bpjs_components = ["BPJS Kesehatan Employee", "BPJS JHT Employee", "BPJS JP Employee"]

        # Check deductions for BPJS components
        if hasattr(slip, "deductions") and slip.deductions:
            for deduction in slip.deductions:
                if deduction.salary_component in bpjs_components and flt(deduction.amount) > 0:
                    return True

        return False

    except Exception as e:
        debug_log(f"Error checking for BPJS components: {str(e)}", "error")
        return False
