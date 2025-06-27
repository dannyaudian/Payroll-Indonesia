# path: payroll_indonesia/payroll_indonesia/salary_slip.py
# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-27 09:44:49 by dannyaudian

from typing import Any, Dict, List, Optional, Tuple, Union
import logging

import frappe
from frappe import _
from frappe.utils import flt, getdate, add_to_date, date_diff

# Import BPJS calculation module
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs
from payroll_indonesia.override.salary_slip.bpjs_calculator import calculate_bpjs_components

# Import centralized tax calculation
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components

# Import standardized cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value, clear_all_caches

# Import constants
from payroll_indonesia.constants import (
    CACHE_MEDIUM,
    CACHE_LONG,
    MAX_DATE_DIFF,
    VALID_TAX_STATUS,
)

# Import validation utilities
from payroll_indonesia.utilities.salary_slip_validator import (
    has_pph21_component,
    has_bpjs_component,
)

# Define exports for proper importing by other modules
__all__ = [
    "calculate_bpjs_for_employee",
    "update_employee_tax_summary",
    "process_salary_slip",
    "verify_bpjs_components",
    "clear_salary_slip_cache",
]

# Type aliases
SalarySlipDoc = Any  # frappe.model.document.Document type for Salary Slip
EmployeeDoc = Any  # frappe.model.document.Document type for Employee


def get_logger() -> logging.Logger:
    """Get properly configured logger for salary slip module."""
    return frappe.logger("salary_slip", with_more_info=True)


def process_salary_slip(doc: SalarySlipDoc, method: Optional[str] = None) -> None:
    """
    Process salary slip with Indonesian payroll components.
    This function is called from hooks and handles different lifecycle events.

    Args:
        doc: The Salary Slip document
        method: Method name that triggered this function
    """
    logger = get_logger()
    
    try:
        # Handle different lifecycle events
        if method == "validate":
            validate_salary_slip(doc)
        elif method == "on_submit":
            on_submit_salary_slip(doc)
        elif method == "on_cancel":
            on_cancel_salary_slip(doc)
        elif method == "after_insert":
            after_insert_salary_slip(doc)
        elif method == "before_save":
            before_save_salary_slip(doc)
        elif method == "after_save":
            after_save_salary_slip(doc)
        else:
            # Default to validation if method not specified
            validate_salary_slip(doc)
            
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # For other errors, log and re-raise
        logger.exception(
            f"Error processing salary slip {getattr(doc, 'name', 'New')}: {e}"
        )
        frappe.throw(
            _("Error processing salary slip: {0}").format(str(e)),
            title=_("Processing Failed")
        )


def validate_salary_slip(doc: SalarySlipDoc) -> None:
    """
    Validate salary slip and calculate Indonesian components.
    Handles BPJS and tax calculations with appropriate error handling.

    Args:
        doc: The Salary Slip document
    """
    try:
        # Initialize default fields if needed
        _initialize_payroll_fields(doc)
        
        # Get employee document
        employee = _get_employee_doc(doc)
        
        # Calculate BPJS components using the current salary slip
        calculate_bpjs_components(doc)
        
        # Calculate tax components using centralized function
        calculate_tax_components(doc, employee)
        
        # Verify BPJS fields are set properly
        _verify_bpjs_fields(doc)
        
        # Calculate and set the bpjs_deductions field (employee contributions only)
        calculate_bpjs_employee_deductions(doc)
        
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Critical validation error - log and throw
        get_logger().exception(
            f"Error validating salary slip {getattr(doc, 'name', 'New')}: {e}"
        )
        frappe.throw(_("Could not validate salary slip: {0}").format(str(e)))


def calculate_bpjs_employee_deductions(doc: SalarySlipDoc) -> float:
    """
    Calculate and store the total BPJS deductions for employee only.
    Sets the value to doc.bpjs_deductions field.

    Args:
        doc: The Salary Slip document
        
    Returns:
        float: Total BPJS deductions for employee
    """
    total_employee_deductions = 0.0
    
    # Sum all BPJS deductions for employee
    if hasattr(doc, "kesehatan_employee"):
        total_employee_deductions += flt(doc.kesehatan_employee)
        
    if hasattr(doc, "jht_employee"):
        total_employee_deductions += flt(doc.jht_employee)
        
    if hasattr(doc, "jp_employee"):
        total_employee_deductions += flt(doc.jp_employee)
    
    # Set the bpjs_deductions field
    if hasattr(doc, "bpjs_deductions"):
        doc.bpjs_deductions = total_employee_deductions
        
        # Try to persist the value using db_set
        try:
            doc.db_set("bpjs_deductions", total_employee_deductions, update_modified=False)
        except Exception:
            # Silently continue if db_set fails (e.g. for new docs)
            pass
    
    return total_employee_deductions


def before_save_salary_slip(doc: SalarySlipDoc) -> None:
    """
    Event hook that runs before a Salary Slip is saved.
    Ensures all calculated fields are up-to-date.

    Args:
        doc: The Salary Slip document
    """
    try:
        # Recalculate BPJS employee deductions before saving
        calculate_bpjs_employee_deductions(doc)
        
    except Exception as e:
        # Non-critical error - log and continue
        get_logger().warning(
            f"Error in before-save processing for {getattr(doc, 'name', 'New')}: {e}"
        )
        frappe.msgprint(
            _("Warning: Error during pre-save processing: {0}").format(str(e)),
            indicator="orange"
        )


def after_save_salary_slip(doc: SalarySlipDoc) -> None:
    """
    Event hook that runs after a Salary Slip is saved.
    Performs final verification of calculated fields.

    Args:
        doc: The Salary Slip document
    """
    try:
        # Verify BPJS components match between tables and custom fields
        verify_bpjs_components(doc)
        
        # Ensure bpjs_deductions field is set correctly
        calculate_bpjs_employee_deductions(doc)
        
    except Exception as e:
        # Non-critical error - log and continue
        get_logger().warning(
            f"Error in post-save processing for {getattr(doc, 'name', 'New')}: {e}"
        )
        frappe.msgprint(
            _("Warning: Error during post-save processing: {0}").format(str(e)),
            indicator="orange"
        )


def on_submit_salary_slip(doc: SalarySlipDoc) -> None:
    """
    Event hook for Salary Slip submission.
    Updates related tax and benefit documents.
    Processes documents that are relevant to PPh 21 tax or BPJS calculations.

    Args:
        doc: The Salary Slip document
    """
    try:
        # Verify BPJS fields one last time before submission
        _verify_bpjs_fields(doc)
        
        # Make sure bpjs_deductions is calculated and set
        calculate_bpjs_employee_deductions(doc)
        
        # Check if the salary slip has PPh 21 component or BPJS component
        # Only process tax summary updates for salary slips with PPh 21 or BPJS component
        if has_pph21_component(doc) or has_bpjs_component(doc):
            get_logger().info(
                f"Salary slip {doc.name} has PPh 21 or BPJS component, updating tax summary"
            )
            
            # Get the bpjs_deductions value to include in the tax summary
            bpjs_deductions = getattr(doc, "bpjs_deductions", 0)
            
            # Enqueue tax summary creation/update job with BPJS deductions
            frappe.enqueue(
                method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary."
                       "employee_tax_summary.create_from_salary_slip",
                queue="long",
                timeout=600,
                salary_slip=doc.name,
                bpjs_deductions=bpjs_deductions,
                is_async=True,
                job_name=f"tax_summary_update_{doc.name}",
                now=False,  # Run in background
            )
            
            # Add note about queued job if payroll_note field exists
            if hasattr(doc, "payroll_note"):
                note = (
                    f"Tax summary update queued in background job: "
                    f"tax_summary_update_{doc.name}"
                )
                current_note = getattr(doc, "payroll_note", "")
                
                if current_note:
                    new_note = f"{current_note}\n{note}"
                else:
                    new_note = note
                    
                try:
                    doc.db_set("payroll_note", new_note, update_modified=False)
                except Exception as e:
                    get_logger().warning(f"Could not update payroll note: {e}")
        else:
            get_logger().info(
                f"Salary slip {doc.name} doesn't have PPh 21 or BPJS component, "
                f"skipping tax summary update"
            )
            
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Critical submission error - log and throw
        get_logger().exception(f"Error processing salary slip submission for {doc.name}: {e}")
        frappe.throw(_("Error processing salary slip submission: {0}").format(str(e)))


def on_cancel_salary_slip(doc: SalarySlipDoc) -> None:
    """
    Event hook for Salary Slip cancellation.
    Reverts related document changes.
    Only processes documents that are or were relevant to PPh 21 tax calculations.

    Args:
        doc: The Salary Slip document
    """
    try:
        # Check if the salary slip has or had a PPh 21 component
        # For cancellation, we check using a more thorough approach
        has_tax_component = has_pph21_component(doc)
        has_bpjs_comp = has_bpjs_component(doc)
        
        # Also check if a tax summary exists for this employee and period
        tax_summary_exists = False
        try:
            year = getdate(doc.end_date).year if hasattr(doc, "end_date") and doc.end_date else None
            if year and hasattr(doc, "employee") and doc.employee:
                tax_summary_exists = frappe.db.exists(
                    "Employee Tax Summary", {"employee": doc.employee, "year": year}
                )
        except Exception as e:
            get_logger().warning(f"Error checking for existing tax summary: {e}")
            
        # Only process if the slip has PPh 21 component, BPJS component, or a tax summary exists
        if has_tax_component or has_bpjs_comp or tax_summary_exists:
            get_logger().info(
                f"Processing tax summary reversion for {doc.name}. "
                f"Has PPh21: {has_tax_component}, Has BPJS: {has_bpjs_comp}, "
                f"Tax summary exists: {tax_summary_exists}"
            )
            
            # Determine tax year
            year = None
            if hasattr(doc, "end_date") and doc.end_date:
                year = getdate(doc.end_date).year
                
            if not year:
                get_logger().warning(
                    f"Could not determine year for tax summary reversion: {doc.name}"
                )
                return
                
            # Enqueue tax summary reversion job
            frappe.enqueue(
                method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary."
                       "employee_tax_summary.update_on_salary_slip_cancel",
                queue="long",
                timeout=300,
                salary_slip=doc.name,
                year=year,
                is_async=True,
                job_name=f"tax_summary_revert_{doc.name}",
                now=False,  # Run in background
            )
            
            # Add note about queued job if payroll_note field exists
            if hasattr(doc, "payroll_note"):
                note = (
                    f"Tax summary reversion queued in background job: "
                    f"tax_summary_revert_{doc.name}"
                )
                current_note = getattr(doc, "payroll_note", "")
                
                if current_note:
                    new_note = f"{current_note}\n{note}"
                else:
                    new_note = note
                    
                try:
                    doc.db_set("payroll_note", new_note, update_modified=False)
                except Exception as e:
                    get_logger().warning(f"Could not update payroll note: {e}")
        else:
            get_logger().info(
                f"Salary slip {doc.name} has no PPh 21 or BPJS component and no tax summary exists, "
                f"skipping tax summary reversion"
            )
            
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise
            
        # Critical cancellation error - log and throw
        get_logger().exception(f"Error processing salary slip cancellation for {doc.name}: {e}")
        frappe.throw(_("Error processing salary slip cancellation: {0}").format(str(e)))


def after_insert_salary_slip(doc: SalarySlipDoc) -> None:
    """
    Event hook that runs after a Salary Slip is created.
    Initializes custom fields required for Indonesian payroll.

    Args:
        doc: The Salary Slip document
    """
    try:
        # Handle initialization only for Salary Slip documents
        if doc.doctype != "Salary Slip":
            return
            
        # Initialize base fields
        _initialize_payroll_fields(doc)
        
        # Initialize tax ID fields
        set_tax_ids_from_employee(doc)
        
    except Exception as e:
        # Non-critical post-creation error - log and continue
        get_logger().warning(
            f"Error in post-creation processing for {getattr(doc, 'name', 'New')}: {e}"
        )
        frappe.msgprint(
            _("Warning: Error during post-creation processing: {0}").format(str(e)),
            indicator="orange"
        )


def _initialize_payroll_fields(doc: SalarySlipDoc) -> Dict[str, Any]:
    """
    Initialize additional payroll fields with default values.
    Ensures all required fields exist with proper default values.

    Args:
        doc: The Salary Slip document
        
    Returns:
        Dict[str, Any]: Dictionary of default values used
    """
    try:
        defaults = {
            "biaya_jabatan": 0,
            "netto": 0,
            "total_bpjs": 0,
            "kesehatan_employee": 0,
            "jht_employee": 0,
            "jp_employee": 0,
            "bpjs_deductions": 0,  # Initialize the new field
            "is_using_ter": 0,
            "ter_rate": 0,
            "ter_category": "",
            "koreksi_pph21": 0,
            "payroll_note": "",
            "npwp": "",
            "ktp": "",
            "is_final_gabung_suami": 0,
        }
        
        # Set defaults for fields that don't exist or are None
        for field, default in defaults.items():
            if not hasattr(doc, field) or getattr(doc, field) is None:
                setattr(doc, field, default)
                # Try to use db_set for persistence
                try:
                    doc.db_set(field, default, update_modified=False)
                except Exception:
                    # Silently continue if db_set fails (e.g. for new docs)
                    pass
                    
        return defaults
        
    except Exception as e:
        # Non-critical error during initialization - log and continue
        get_logger().warning(
            f"Error initializing payroll fields for {getattr(doc, 'name', 'New')}: {e}"
        )
        frappe.msgprint(
            _("Warning: Error initializing payroll fields: {0}").format(str(e)),
            indicator="orange"
        )
        return {}


def _verify_bpjs_fields(doc: SalarySlipDoc) -> None:
    """
    Verify that BPJS-related fields are properly set and are numeric.

    Args:
        doc: The Salary Slip document
        
    Raises:
        frappe.ValidationError: If any BPJS field is not numeric
    """
    bpjs_fields = [
        "kesehatan_employee", "jht_employee", "jp_employee", 
        "total_bpjs", "bpjs_deductions"
    ]
    
    for field in bpjs_fields:
        if not hasattr(doc, field):
            frappe.throw(
                _("Missing BPJS field: {0}. Please check custom fields configuration.").format(
                    field
                ),
                title=_("Configuration Error")
            )
            
        value = getattr(doc, field)
        if value is None or not isinstance(value, (int, float)):
            frappe.throw(
                _("BPJS field {0} must be numeric. Current value: {1}").format(field, str(value)),
                title=_("Invalid BPJS Field")
            )


def _get_employee_doc(doc: SalarySlipDoc) -> EmployeeDoc:
    """
    Retrieves the complete Employee document for the current salary slip.

    Args:
        doc: The Salary Slip document
        
    Returns:
        Employee document with all fields
        
    Raises:
        frappe.ValidationError: If employee cannot be found or retrieved
    """
    if not hasattr(doc, "employee") or not doc.employee:
        # Critical validation error - employee is required
        frappe.throw(_("Salary Slip must have an employee assigned"), title=_("Missing Employee"))
        
    try:
        return frappe.get_doc("Employee", doc.employee)
    except Exception as e:
        # Critical validation error - employee must exist
        get_logger().exception(
            f"Error retrieving Employee {doc.employee} for salary slip "
            f"{getattr(doc, 'name', 'New')}: {e}"
        )
        frappe.throw(
            _("Could not retrieve Employee {0}: {1}").format(doc.employee, str(e)),
            title=_("Employee Not Found")
        )


def set_tax_ids_from_employee(doc: SalarySlipDoc) -> None:
    """
    Set tax ID fields (NPWP, KTP) from employee record.

    Args:
        doc: The Salary Slip document
    """
    try:
        if not hasattr(doc, "employee") or not doc.employee:
            return
            
        # Get NPWP and KTP from employee if they're not already set
        if hasattr(doc, "npwp") and not doc.npwp:
            employee_npwp = frappe.db.get_value("Employee", doc.employee, "npwp")
            if employee_npwp:
                doc.npwp = employee_npwp
                doc.db_set("npwp", employee_npwp, update_modified=False)
                
        if hasattr(doc, "ktp") and not doc.ktp:
            employee_ktp = frappe.db.get_value("Employee", doc.employee, "ktp")
            if employee_ktp:
                doc.ktp = employee_ktp
                doc.db_set("ktp", employee_ktp, update_modified=False)
                
    except Exception as e:
        # Non-critical error - log and continue
        get_logger().warning(
            f"Error setting tax IDs from employee for {getattr(doc, 'name', 'New')}: {e}"
        )
        frappe.msgprint(
            _("Warning: Could not set tax IDs from employee record: {0}").format(str(e)),
            indicator="orange"
        )


def clear_salary_slip_cache() -> Dict[str, str]:
    """
    Clear all caches related to salary slip and tax calculations.
    This function is used by scheduler events and can be called manually.

    Returns:
        Dict[str, str]: Operation status and message
    """
    try:
        # Use the centralized cache clearing function
        clear_all_caches()
        
        # Log success
        get_logger().info("Salary slip caches cleared successfully")
        return {"status": "success", "message": "All caches cleared successfully"}
        
    except Exception as e:
        # Non-critical error during cache clearing - log and return error
        get_logger().exception(f"Error clearing caches: {e}")
        return {"status": "error", "message": f"Error clearing caches: {str(e)}"}


def calculate_bpjs_for_employee(
    employee_id: str, 
    base_salary: Optional[float] = None, 
    slip: Optional[SalarySlipDoc] = None
) -> Dict[str, float]:
    """
    Calculate BPJS components for an employee.
    Separates employee and employer contributions.

    Args:
        employee_id: Employee ID to calculate for
        base_salary: Optional base salary amount
        slip: Optional Salary Slip document to update
        
    Returns:
        Dict[str, float]: Calculated BPJS values with separate employee/employer contributions
    """
    try:
        # Get employee document
        employee = frappe.get_doc("Employee", employee_id)
        
        # If base salary not provided, try to get from employee
        if base_salary is None or base_salary <= 0:
            if hasattr(employee, "gross_salary") and employee.gross_salary > 0:
                base_salary = flt(employee.gross_salary)
            else:
                # Use default from existing configurations
                from payroll_indonesia.constants import DEFAULT_UMR
                
                base_salary = DEFAULT_UMR
                get_logger().info(
                    f"No base salary provided for {employee_id}, using DEFAULT_UMR: {DEFAULT_UMR}"
                )
                
        # Use the hitung_bpjs function with the doc parameter
        bpjs_values = hitung_bpjs(employee, base_salary, doc=slip)
        
        # If slip provided, update the bpjs_deductions field
        if slip:
            # Calculate employee-only BPJS deductions
            employee_deductions = (
                bpjs_values.get("kesehatan_employee", 0) +
                bpjs_values.get("jht_employee", 0) +
                bpjs_values.get("jp_employee", 0)
            )
            
            # Set the bpjs_deductions field
            if hasattr(slip, "bpjs_deductions"):
                slip.bpjs_deductions = employee_deductions
                try:
                    slip.db_set("bpjs_deductions", employee_deductions, update_modified=False)
                except Exception:
                    pass
                    
            # Verify BPJS fields
            _verify_bpjs_fields(slip)
            
        return bpjs_values
        
    except Exception as e:
        get_logger().exception(f"Error calculating BPJS for employee {employee_id}: {e}")
        frappe.throw(_("Error calculating BPJS: {0}").format(str(e)))


def verify_bpjs_components(slip: SalarySlipDoc) -> Dict[str, Any]:
    """
    Verify that BPJS components in the salary slip are correct.
    Updates custom fields from component rows if found.
    Also updates the bpjs_deductions field with employee contributions.

    Args:
        slip: Salary slip document
        
    Returns:
        Dict[str, Any]: Verification results
        
    Raises:
        frappe.ValidationError: If total_bpjs differs significantly from component sum
    """
    log = get_logger()
    
    # Initialize result
    result = {
        "all_zero": True,
        "kesehatan_found": False,
        "jht_found": False,
        "jp_found": False,
        "total": 0,
        "employee_total": 0,  # Track employee contributions separately
        "kesehatan_amount": 0,
        "jht_amount": 0,
        "jp_amount": 0,
    }
    
    try:
        # Debug log at start of verification
        log.debug(f"Starting BPJS verification for slip {getattr(slip, 'name', 'unknown')}")
        
        # Check for BPJS components in deductions
        if not hasattr(slip, "deductions") or not slip.deductions:
            log.info(f"No deductions found in slip {getattr(slip, 'name', 'unknown')}")
            return result
            
        # Check each deduction component
        for deduction in slip.deductions:
            if deduction.salary_component == "BPJS Kesehatan Employee":
                result["kesehatan_found"] = True
                amount = flt(deduction.amount)
                result["kesehatan_amount"] = amount
                if amount > 0:
                    result["all_zero"] = False
                result["total"] += amount
                result["employee_total"] += amount
                
                # Update custom field from deduction row
                if hasattr(slip, "kesehatan_employee"):
                    slip.kesehatan_employee = amount
                    slip.db_set("kesehatan_employee", amount, update_modified=False)
                    
            elif deduction.salary_component == "BPJS JHT Employee":
                result["jht_found"] = True
                amount = flt(deduction.amount)
                result["jht_amount"] = amount
                if amount > 0:
                    result["all_zero"] = False
                result["total"] += amount
                result["employee_total"] += amount
                
                # Update custom field from deduction row
                if hasattr(slip, "jht_employee"):
                    slip.jht_employee = amount
                    slip.db_set("jht_employee", amount, update_modified=False)
                    
            elif deduction.salary_component == "BPJS JP Employee":
                result["jp_found"] = True
                amount = flt(deduction.amount)
                result["jp_amount"] = amount
                if amount > 0:
                    result["all_zero"] = False
                result["total"] += amount
                result["employee_total"] += amount
                
                # Update custom field from deduction row
                if hasattr(slip, "jp_employee"):
                    slip.jp_employee = amount
                    slip.db_set("jp_employee", amount, update_modified=False)
                    
        # Update doc.total_bpjs to match component sum
        if hasattr(slip, "total_bpjs"):
            # Check for inconsistency between total_bpjs and component sum
            current_total = flt(slip.total_bpjs)
            if abs(current_total - result["total"]) > 1:  # Allow 1 IDR difference for rounding
                log.warning(
                    f"BPJS total mismatch in {getattr(slip, 'name', 'unknown')}: "
                    f"total_bpjs={current_total}, component sum={result['total']}"
                )
                # Raise validation error for significant differences
                frappe.throw(
                    _(
                        "BPJS total ({0}) differs from sum of components ({1}). "
                        "Please recalculate BPJS components."
                    ).format(current_total, result["total"]),
                    title=_("BPJS Calculation Inconsistency")
                )
                
            # Update to ensure consistency
            slip.total_bpjs = result["total"]
            slip.db_set("total_bpjs", result["total"], update_modified=False)
            
        # Update the bpjs_deductions field with employee contributions only
        if hasattr(slip, "bpjs_deductions"):
            slip.bpjs_deductions = result["employee_total"]
            slip.db_set("bpjs_deductions", result["employee_total"], update_modified=False)
            
        # Log verification results
        log.debug(
            f"BPJS verification complete for {getattr(slip, 'name', 'unknown')}: "
            f"kesehatan={result['kesehatan_amount']}, jht={result['jht_amount']}, "
            f"jp={result['jp_amount']}, total={result['total']}, "
            f"employee_total={result['employee_total']}"
        )
        
        return result
        
    except Exception as e:
        # Non-critical verification error - log and return default result
        log.exception(f"Error verifying BPJS components: {e}")
        frappe.msgprint(_("Warning: Could not verify BPJS components."), indicator="orange")
        # Return default result on error
        return result


def update_employee_tax_summary(
    slip_name: str, 
    bpjs_deductions: Optional[float] = None,
    is_async: bool = True
) -> Dict[str, Any]:
    """
    Update the Employee Tax Summary from a salary slip.
    Includes BPJS deductions in the update.

    Args:
        slip_name: Name of the salary slip document
        bpjs_deductions: Optional BPJS deductions amount (employee contributions only)
        is_async: Whether to process in background
        
    Returns:
        Dict[str, Any]: Status and details of the operation
    """
    try:
        # Get the salary slip document
        slip = frappe.get_doc("Salary Slip", slip_name)
        
        # Ensure bpjs_deductions is set
        if bpjs_deductions is None and hasattr(slip, "bpjs_deductions"):
            bpjs_deductions = flt(slip.bpjs_deductions)
            
        # If still None, calculate it
        if bpjs_deductions is None:
            bpjs_deductions = calculate_bpjs_employee_deductions(slip)
            
        # Use background job if requested
        if is_async:
            # Queue background job
            frappe.enqueue(
                method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary."
                       "employee_tax_summary.create_from_salary_slip",
                queue="long",
                timeout=600,
                salary_slip=slip_name,
                bpjs_deductions=bpjs_deductions,
                is_async=True,
                job_name=f"tax_summary_update_{slip_name}",
                now=False,
            )
            
            return {
                "status": "queued",
                "message": f"Tax summary update queued for {slip_name}",
                "bpjs_deductions": bpjs_deductions
            }
        else:
            # Process synchronously
            from payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary import create_from_salary_slip
            
            result = create_from_salary_slip(slip_name, bpjs_deductions=bpjs_deductions)
            return {
                "status": "completed",
                "message": f"Tax summary updated for {slip_name}",
                "result": result,
                "bpjs_deductions": bpjs_deductions
            }
            
    except Exception as e:
        get_logger().exception(f"Error updating tax summary for {slip_name}: {e}")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def refresh_slip_calculations(slip_name: str) -> Dict[str, Any]:
    """
    Refresh all calculations for a salary slip.
    This includes BPJS and tax components.

    Args:
        slip_name: Name of the salary slip document
        
    Returns:
        Dict[str, Any]: Status and details of the operation
    """
    try:
        # Get the salary slip document
        slip = frappe.get_doc("Salary Slip", slip_name)
        
        # Validate the salary slip
        validate_salary_slip(slip)
        
        # Calculate and update BPJS employee deductions
        bpjs_deductions = calculate_bpjs_employee_deductions(slip)
        
        # Save the document
        slip.save()
        
        return {
            "status": "success",
            "message": f"Calculations refreshed for {slip_name}",
            "bpjs_deductions": bpjs_deductions,
            "total_bpjs": getattr(slip, "total_bpjs", 0)
        }
        
    except Exception as e:
        get_logger().exception(f"Error refreshing calculations for {slip_name}: {e}")
        frappe.throw(_("Error refreshing calculations: {0}").format(str(e)))
