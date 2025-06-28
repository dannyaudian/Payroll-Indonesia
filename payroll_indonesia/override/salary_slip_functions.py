# path: payroll_indonesia/payroll_indonesia/salary_slip_functions.py
# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-28 03:12:38 by dannyaudian

from typing import Any, Dict, Optional
import logging

import frappe
from frappe import _
from frappe.utils import flt, getdate

# Import BPJS calculation functions
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs
from payroll_indonesia.override.salary_slip.bpjs_calculator import calculate_bpjs_components

# Import centralized tax calculation function
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components

# Import YTD calculation function
from payroll_indonesia.override.salary_slip import calculate_ytd_and_ytm

# Import standardized error logging and cache utilities
from payroll_indonesia.utilities.cache_utils import clear_all_caches, schedule_cache_clearing

# Import salary slip validation utility
from payroll_indonesia.utilities.salary_slip_validator import has_pph21_component

__all__ = [
    "validate_salary_slip",
    "on_submit_salary_slip",
    "on_cancel_salary_slip",
    "after_insert_salary_slip",
    "clear_caches",
    "has_bpjs_component",
]

# Type aliases
SalarySlipDoc = Any  # frappe.model.document.Document type for Salary Slip
EmployeeDoc = Any  # frappe.model.document.Document type for Employee


def get_logger() -> logging.Logger:
    """Get properly configured logger for salary slip functions module."""
    return frappe.logger("salary_slip_functions", with_more_info=True)


def validate_salary_slip(doc: SalarySlipDoc, method: Optional[str] = None) -> None:
    """
    Event hook for validating Salary Slip.
    Handles tax and BPJS calculations with appropriate error handling.

    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # Initialize default fields if needed
        _initialize_payroll_fields(doc)

        # Get employee document
        employee = _get_employee_doc(doc)

        # Calculate BPJS components using the new centralizing function
        # This will automatically update the required fields
        calculate_bpjs_components(doc)

        # Verify BPJS fields are set properly
        _verify_bpjs_fields(doc)
        
        # Calculate and set YTD values
        ytd_vals = calculate_ytd_and_ytm(doc)
        doc.db_set("ytd_gross_pay", ytd_vals["ytd_gross"], update_modified=False)
        doc.db_set("ytd_bpjs_deductions", ytd_vals["ytd_bpjs"], update_modified=False)

        # Calculate tax components using centralized function
        calculate_tax_components(doc, employee)

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # Critical validation error - log and throw
        get_logger().exception(f"Error validating salary slip {getattr(doc, 'name', 'New')}: {e}")
        frappe.throw(_("Could not validate salary slip: {0}").format(str(e)))


def has_bpjs_component(doc: SalarySlipDoc) -> bool:
    """
    Check if the salary slip has any BPJS component in its deductions.
    
    Args:
        doc: The Salary Slip document
        
    Returns:
        bool: True if any BPJS component is found, False otherwise
    """
    if not hasattr(doc, "deductions") or not doc.deductions:
        return False
        
    bpjs_components = [
        "BPJS JHT Employee",
        "BPJS JP Employee",
        "BPJS Kesehatan Employee"
    ]
    
    for deduction in doc.deductions:
        if hasattr(deduction, "salary_component") and deduction.salary_component in bpjs_components:
            return True
            
    return False


def on_submit_salary_slip(doc: SalarySlipDoc, method: Optional[str] = None) -> None:
    """
    Event hook for Salary Slip submission.
    Updates related tax and benefit documents.
    Only processes documents that are relevant to PPh 21 tax calculations.

    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # Verify BPJS fields one last time before submission
        _verify_bpjs_fields(doc)

        # Verify settings for TER if using TER method
        if getattr(doc, "is_using_ter", 0):
            # Verify TER category is set - warning only
            if not getattr(doc, "ter_category", ""):
                get_logger().warning(f"Using TER but no category set for {doc.name}")
                frappe.msgprint(_("Warning: Using TER but no category set"), indicator="orange")

            # Verify TER rate is set - warning only
            if not getattr(doc, "ter_rate", 0):
                get_logger().warning(f"Using TER but no rate set for {doc.name}")
                frappe.msgprint(_("Warning: Using TER but no rate set"), indicator="orange")

        # Check if the salary slip has PPh 21 component or BPJS component
        # Only process tax summary updates for salary slips with PPh 21 or BPJS component
        if has_pph21_component(doc) or has_bpjs_component(doc):
            get_logger().info(
                f"Salary slip {doc.name} has PPh 21 or BPJS component, updating tax summary"
            )

            # Enqueue tax summary creation/update job
            frappe.enqueue(
                method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.create_from_salary_slip",
                queue="long",
                timeout=600,
                salary_slip=doc.name,
                is_async=True,
                job_name=f"tax_summary_update_{doc.name}",
                now=False,  # Run in background
            )

            # Add note about queued job if payroll_note field exists
            if hasattr(doc, "payroll_note"):
                note = f"Tax summary update queued in background job: tax_summary_update_{doc.name}"
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


def on_cancel_salary_slip(doc: SalarySlipDoc, method: Optional[str] = None) -> None:
    """
    Event hook for Salary Slip cancellation.
    Reverts related document changes.
    Only processes documents that are or were relevant to PPh 21 tax calculations.

    Args:
        doc: The Salary Slip document
        method: Method name (not used)
    """
    try:
        # Check if the salary slip has or had a PPh 21 component
        # For cancellation, we check using a more thorough approach since the
        # component might have been present in the original submission
        has_tax_component = has_pph21_component(doc)

        # Also check if a tax summary exists for this employee and period
        # since we might need to update it even if the PPh 21 component is no longer visible
        tax_summary_exists = False
        try:
            year = getdate(doc.end_date).year if hasattr(doc, "end_date") and doc.end_date else None
            if year and hasattr(doc, "employee") and doc.employee:
                tax_summary_exists = frappe.db.exists(
                    "Employee Tax Summary", {"employee": doc.employee, "year": year}
                )
        except Exception as e:
            get_logger().warning(f"Error checking for existing tax summary: {e}")

        # Only process if the slip has PPh 21 component or a tax summary exists
        if has_tax_component or tax_summary_exists:
            get_logger().info(
                f"Processing tax summary reversion for {doc.name}. "
                f"Has PPh21: {has_tax_component}, Tax summary exists: {tax_summary_exists}"
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
                method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.update_on_salary_slip_cancel",
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
                    f"Tax summary reversion queued in background job: tax_summary_revert_{doc.name}"
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
                f"Salary slip {doc.name} has no PPh 21 component and no tax summary exists, "
                f"skipping tax summary reversion"
            )

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # Critical cancellation error - log and throw
        get_logger().exception(f"Error processing salary slip cancellation for {doc.name}: {e}")
        frappe.throw(_("Error processing salary slip cancellation: {0}").format(str(e)))


def after_insert_salary_slip(doc: SalarySlipDoc, method: Optional[str] = None) -> None:
    """
    Event hook that runs after a Salary Slip is created.
    Initializes custom fields required for Indonesian payroll.

    Args:
        doc: The Salary Slip document
        method: Method name (not used)
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
            indicator="orange",
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
            "is_using_ter": 0,
            "ter_rate": 0,
            "ter_category": "",
            "koreksi_pph21": 0,
            "payroll_note": "",
            "npwp": "",
            "ktp": "",
            "is_final_gabung_suami": 0,
            "ytd_gross_pay": 0.0,
            "ytd_bpjs_deductions": 0.0,
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
            _("Warning: Error initializing payroll fields: {0}").format(str(e)), indicator="orange"
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
    bpjs_fields = ["kesehatan_employee", "jht_employee", "jp_employee", "total_bpjs"]

    for field in bpjs_fields:
        if not hasattr(doc, field):
            frappe.throw(
                _("Missing BPJS field: {0}. Please check custom fields configuration.").format(
                    field
                ),
                title=_("Configuration Error"),
            )

        value = getattr(doc, field)
        if value is None or not isinstance(value, (int, float)):
            frappe.throw(
                _("BPJS field {0} must be numeric. Current value: {1}").format(field, str(value)),
                title=_("Invalid BPJS Field"),
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
            title=_("Employee Not Found"),
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
            indicator="orange",
        )


def clear_caches() -> Dict[str, str]:
    """
    Clear all caches related to salary slip and tax calculations.
    This function is used by scheduler events and can be called manually.

    Returns:
        Dict[str, str]: Operation status and message
    """
    try:
        # Use the centralized cache clearing function
        clear_all_caches()

        # Schedule next cache clear in 30 minutes
        schedule_cache_clearing(minutes=30)

        # Log success
        get_logger().info("Salary slip caches cleared successfully")
        return {"status": "success", "message": "All caches cleared successfully"}

    except Exception as e:
        # Non-critical error during cache clearing - log and return error
        get_logger().exception(f"Error clearing caches: {e}")
        return {"status": "error", "message": f"Error clearing caches: {str(e)}"}


def calculate_bpjs_for_employee(
    employee_id: str, base_salary: Optional[float] = None, slip: Optional[SalarySlipDoc] = None
) -> Dict[str, float]:
    """
    Calculate BPJS components for an employee.
    Updated to use the new BPJS calculation function.

    Args:
        employee_id: Employee ID to calculate for
        base_salary: Optional base salary amount
        slip: Optional Salary Slip document to update

    Returns:
        Dict[str, float]: Calculated BPJS values
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

        # Use the new hitung_bpjs function with the doc parameter
        bpjs_values = hitung_bpjs(employee, base_salary, doc=slip)

        # If slip provided, verify BPJS fields
        if slip:
            _verify_bpjs_fields(slip)

        return bpjs_values

    except Exception as e:
        get_logger().exception(f"Error calculating BPJS for employee {employee_id}: {e}")
        frappe.throw(_("Error calculating BPJS: {0}").format(str(e)))

def calculate_total_bpjs(doc):
    """
    Calculate and set total BPJS deductions
    
    Args:
        doc: Salary slip document
    """
    bpjs_total = 0
    
    # Sum up all BPJS components from deductions
    if hasattr(doc, "deductions") and doc.deductions:
        for deduction in doc.deductions:
            component_name = deduction.salary_component
            if any(bpjs_type in component_name for bpjs_type in 
                  ["BPJS Kesehatan", "BPJS JHT", "BPJS JP", "BPJS JKK", "BPJS JKM"]):
                bpjs_total += flt(deduction.amount)
    
    # Store total in bpjs_deductions field
    if hasattr(doc, "bpjs_deductions"):
        doc.bpjs_deductions = bpjs_total
    else:
        setattr(doc, "bpjs_deductions", bpjs_total)
    
    # Update database field directly to avoid another save
    if hasattr(doc, "name") and doc.name:
        try:
            doc.db_set("bpjs_deductions", bpjs_total, update_modified=False)
        except Exception as e:
            # Non-critical error - log but continue
            frappe.logger("salary_slip").warning(f"Error saving bpjs_deductions for {doc.name}: {e}")

def set_ytd_fields(doc, values):
    """
    Set YTD fields on the salary slip document and persist to database.
    
    Args:
        doc: Salary slip document
        values: Dictionary containing YTD values including ytd_gross and ytd_bpjs
    """
    try:
        # Set ytd_gross_pay from ytd_gross in values
        if hasattr(doc, "ytd_gross_pay"):
            doc.ytd_gross_pay = values.get("ytd_gross", 0.0)
        else:
            setattr(doc, "ytd_gross_pay", values.get("ytd_gross", 0.0))
        
        # Set ytd_bpjs_deductions from ytd_bpjs in values
        if hasattr(doc, "ytd_bpjs_deductions"):
            doc.ytd_bpjs_deductions = values.get("ytd_bpjs", 0.0)
        else:
            setattr(doc, "ytd_bpjs_deductions", values.get("ytd_bpjs", 0.0))
        
        # Persist to database if document has a name
        if hasattr(doc, "name") and doc.name:
            try:
                doc.db_set("ytd_gross_pay", doc.ytd_gross_pay, update_modified=False)
                doc.db_set("ytd_bpjs_deductions", doc.ytd_bpjs_deductions, 
                          update_modified=False)
                
                # Log success
                frappe.logger("salary_slip").debug(
                    f"YTD fields set for {doc.name}: "
                    f"gross={doc.ytd_gross_pay}, bpjs={doc.ytd_bpjs_deductions}"
                )
            except Exception as e:
                # Non-critical error - log and continue
                frappe.logger("salary_slip").warning(f"Error persisting YTD fields for {doc.name}: {e}")
    except Exception as e:
        # Non-critical error - log and continue
        frappe.logger("salary_slip").warning(
            f"Error setting YTD fields for "
            f"{doc.name if hasattr(doc, 'name') else 'New'}: {e}"
        )
