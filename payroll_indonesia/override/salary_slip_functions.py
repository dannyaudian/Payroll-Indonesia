# path: payroll_indonesia/override/salary_slip_functions.py
# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from typing import Any, Dict, Optional
import logging

import frappe
from frappe import _
from frappe.utils import flt, getdate

# Import BPJS calculation functions
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import hitung_bpjs
from payroll_indonesia.override.salary_slip.bpjs_calculator import calculate_bpjs_components
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components
from payroll_indonesia.payroll_indonesia.salary_slip import calculate_ytd_and_ytm
from payroll_indonesia.utilities.cache_utils import clear_all_caches, schedule_cache_clearing
from payroll_indonesia.utilities.salary_slip_validator import has_pph21_component
from payroll_indonesia.constants import BPJS_COMPONENTS, DEFAULT_UMR

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
    """Validate salary slip and handle tax and BPJS calculations."""
    try:
        # Initialize default fields if needed
        initialize_payroll_fields(doc)

        # Get employee document
        employee = get_employee_doc(doc)

        # Calculate BPJS components
        calculate_bpjs_components(doc)

        # Verify BPJS fields are set properly
        verify_bpjs_fields(doc)
        
        # Calculate and set YTD values
        update_ytd_values(doc)

        # Calculate tax components using centralized function
        calculate_tax_components(doc, employee)

    except Exception as e:
        handle_validation_error(e, doc)


def has_bpjs_component(doc: SalarySlipDoc) -> bool:
    """Check if salary slip has any BPJS component in its deductions."""
    if not hasattr(doc, "deductions") or not doc.deductions:
        return False
    
    for deduction in doc.deductions:
        if (hasattr(deduction, "salary_component") and 
                deduction.salary_component in BPJS_COMPONENTS):
            return True
            
    return False


def on_submit_salary_slip(doc: SalarySlipDoc, method: Optional[str] = None) -> None:
    """Process salary slip submission and update related tax documents."""
    try:
        # Verify BPJS fields one last time before submission
        verify_bpjs_fields(doc)

        # Verify TER settings if applicable
        verify_ter_settings(doc)

        # Process tax and BPJS updates if relevant
        if has_pph21_component(doc) or has_bpjs_component(doc):
            queue_tax_summary_update(doc)
        else:
            log_skipped_tax_update(doc)

    except Exception as e:
        handle_submission_error(e, doc)


def on_cancel_salary_slip(doc: SalarySlipDoc, method: Optional[str] = None) -> None:
    """Revert related document changes on salary slip cancellation."""
    try:
        # Check if needs tax processing
        has_tax_component = has_pph21_component(doc)
        tax_summary_exists = check_tax_summary_exists(doc)

        if has_tax_component or tax_summary_exists:
            year = get_tax_year(doc)
            if year:
                queue_tax_summary_reversion(doc, year)
        else:
            log_skipped_tax_reversion(doc)

    except Exception as e:
        handle_cancellation_error(e, doc)


def after_insert_salary_slip(doc: SalarySlipDoc, method: Optional[str] = None) -> None:
    """Initialize custom fields required for Indonesian payroll after creation."""
    try:
        # Handle initialization only for Salary Slip documents
        if doc.doctype != "Salary Slip":
            return

        # Initialize base fields
        initialize_payroll_fields(doc)

        # Initialize tax ID fields
        set_tax_ids_from_employee(doc)

    except Exception as e:
        handle_post_creation_error(e, doc)


def initialize_payroll_fields(doc: SalarySlipDoc) -> Dict[str, Any]:
    """Initialize all required payroll fields with default values."""
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
                try:
                    doc.db_set(field, default, update_modified=False)
                except Exception:
                    # Silently continue if db_set fails (e.g. for new docs)
                    pass

        return defaults

    except Exception as e:
        get_logger().warning(
            f"Error initializing payroll fields for {getattr(doc, 'name', 'New')}: {e}"
        )
        frappe.msgprint(
            _("Warning: Error initializing payroll fields: {0}").format(str(e)), 
            indicator="orange"
        )
        return {}


def verify_bpjs_fields(doc: SalarySlipDoc) -> None:
    """Verify that BPJS-related fields are properly set and are numeric."""
    bpjs_fields = ["kesehatan_employee", "jht_employee", "jp_employee", "total_bpjs"]

    for field in bpjs_fields:
        if not hasattr(doc, field):
            frappe.throw(
                _("Missing BPJS field: {0}. Check custom fields configuration.").format(field),
                title=_("Configuration Error"),
            )

        value = getattr(doc, field)
        if value is None or not isinstance(value, (int, float)):
            frappe.throw(
                _("BPJS field {0} must be numeric. Current value: {1}").format(field, str(value)),
                title=_("Invalid BPJS Field"),
            )


def get_employee_doc(doc: SalarySlipDoc) -> EmployeeDoc:
    """Retrieve the complete Employee document for the current salary slip."""
    if not hasattr(doc, "employee") or not doc.employee:
        frappe.throw(_("Salary Slip must have an employee assigned"), 
                    title=_("Missing Employee"))

    try:
        return frappe.get_doc("Employee", doc.employee)
    except Exception as e:
        get_logger().exception(
            f"Error retrieving Employee {doc.employee} for salary slip "
            f"{getattr(doc, 'name', 'New')}: {e}"
        )
        frappe.throw(
            _("Could not retrieve Employee {0}: {1}").format(doc.employee, str(e)),
            title=_("Employee Not Found"),
        )


def set_tax_ids_from_employee(doc: SalarySlipDoc) -> None:
    """Set tax ID fields (NPWP, KTP) from employee record."""
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
        get_logger().warning(
            f"Error setting tax IDs from employee for {getattr(doc, 'name', 'New')}: {e}"
        )
        frappe.msgprint(
            _("Warning: Could not set tax IDs from employee record: {0}").format(str(e)),
            indicator="orange",
        )


def clear_caches() -> Dict[str, str]:
    """Clear all caches related to salary slip and tax calculations."""
    try:
        # Use the centralized cache clearing function
        clear_all_caches()

        # Schedule next cache clear in 30 minutes
        schedule_cache_clearing(minutes=30)

        # Log success
        get_logger().info("Salary slip caches cleared successfully")
        return {"status": "success", "message": "All caches cleared successfully"}

    except Exception as e:
        get_logger().exception(f"Error clearing caches: {e}")
        return {"status": "error", "message": f"Error clearing caches: {str(e)}"}


def calculate_bpjs_for_employee(
    employee_id: str, base_salary: Optional[float] = None, slip: Optional[SalarySlipDoc] = None
) -> Dict[str, float]:
    """Calculate BPJS components for an employee."""
    try:
        # Get employee document
        employee = frappe.get_doc("Employee", employee_id)

        # If base salary not provided, try to get from employee
        if base_salary is None or base_salary <= 0:
            base_salary = get_base_salary_for_bpjs(employee)

        # Use the BPJS calculation function with the doc parameter
        bpjs_values = hitung_bpjs(employee, base_salary, doc=slip)

        # If slip provided, verify BPJS fields
        if slip:
            verify_bpjs_fields(slip)

        return bpjs_values

    except Exception as e:
        get_logger().exception(f"Error calculating BPJS for employee {employee_id}: {e}")
        frappe.throw(_("Error calculating BPJS: {0}").format(str(e)))


def get_base_salary_for_bpjs(employee: EmployeeDoc) -> float:
    """Determine base salary for BPJS calculations."""
    if hasattr(employee, "gross_salary") and employee.gross_salary > 0:
        return flt(employee.gross_salary)
    else:
        get_logger().info(
            f"No base salary for {employee.name}, using DEFAULT_UMR: {DEFAULT_UMR}"
        )
        return DEFAULT_UMR


def update_ytd_values(doc: SalarySlipDoc) -> None:
    """Calculate and update Year-to-Date values on the salary slip."""
    ytd_vals = calculate_ytd_and_ytm(doc)
    doc.db_set("ytd_gross_pay", ytd_vals["ytd_gross"], update_modified=False)
    doc.db_set("ytd_bpjs_deductions", ytd_vals["ytd_bpjs"], update_modified=False)


def verify_ter_settings(doc: SalarySlipDoc) -> None:
    """Verify Tax Exemption Rule settings if enabled."""
    if not getattr(doc, "is_using_ter", 0):
        return
        
    # Verify TER category is set - warning only
    if not getattr(doc, "ter_category", ""):
        get_logger().warning(f"Using TER but no category set for {doc.name}")
        frappe.msgprint(_("Warning: Using TER but no category set"), indicator="orange")

    # Verify TER rate is set - warning only
    if not getattr(doc, "ter_rate", 0):
        get_logger().warning(f"Using TER but no rate set for {doc.name}")
        frappe.msgprint(_("Warning: Using TER but no rate set"), indicator="orange")


def queue_tax_summary_update(doc: SalarySlipDoc) -> None:
    """Queue background job to update tax summary for the salary slip."""
    get_logger().info(
        f"Salary slip {doc.name} has PPh 21 or BPJS component, updating tax summary"
    )

    # Enqueue tax summary creation/update job
    frappe.enqueue(
        method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary"
               ".employee_tax_summary.create_from_salary_slip",
        queue="long",
        timeout=600,
        salary_slip=doc.name,
        is_async=True,
        job_name=f"tax_summary_update_{doc.name}",
        now=False,  # Run in background
    )

    add_payroll_note(doc, f"Tax summary update queued: tax_summary_update_{doc.name}")


def log_skipped_tax_update(doc: SalarySlipDoc) -> None:
    """Log information about skipping tax summary update."""
    get_logger().info(
        f"Salary slip {doc.name} doesn't have PPh 21 or BPJS component, "
        f"skipping tax summary update"
    )


def check_tax_summary_exists(doc: SalarySlipDoc) -> bool:
    """Check if a tax summary exists for the employee and period."""
    try:
        year = get_tax_year(doc)
        if year and hasattr(doc, "employee") and doc.employee:
            return frappe.db.exists(
                "Employee Tax Summary", {"employee": doc.employee, "year": year}
            )
        return False
    except Exception as e:
        get_logger().warning(f"Error checking for existing tax summary: {e}")
        return False


def get_tax_year(doc: SalarySlipDoc) -> Optional[int]:
    """Get the tax year from the salary slip end date."""
    if hasattr(doc, "end_date") and doc.end_date:
        return getdate(doc.end_date).year
    return None


def queue_tax_summary_reversion(doc: SalarySlipDoc, year: int) -> None:
    """Queue background job to revert tax summary for cancelled salary slip."""
    get_logger().info(
        f"Processing tax summary reversion for {doc.name}."
    )

    # Enqueue tax summary reversion job
    frappe.enqueue(
        method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary"
               ".employee_tax_summary.update_on_salary_slip_cancel",
        queue="long",
        timeout=300,
        salary_slip=doc.name,
        year=year,
        is_async=True,
        job_name=f"tax_summary_revert_{doc.name}",
        now=False,  # Run in background
    )

    add_payroll_note(doc, f"Tax summary reversion queued: tax_summary_revert_{doc.name}")


def log_skipped_tax_reversion(doc: SalarySlipDoc) -> None:
    """Log information about skipping tax summary reversion."""
    get_logger().info(
        f"Salary slip {doc.name} has no PPh 21 component and no tax summary exists, "
        f"skipping tax summary reversion"
    )


def add_payroll_note(doc: SalarySlipDoc, note: str) -> None:
    """Add a note to the payroll_note field."""
    if not hasattr(doc, "payroll_note"):
        return
        
    current_note = getattr(doc, "payroll_note", "")
    new_note = f"{current_note}\n{note}" if current_note else note

    try:
        doc.db_set("payroll_note", new_note, update_modified=False)
    except Exception as e:
        get_logger().warning(f"Could not update payroll note: {e}")


def handle_validation_error(e: Exception, doc: SalarySlipDoc) -> None:
    """Handle exceptions during salary slip validation."""
    # Handle ValidationError separately
    if isinstance(e, frappe.exceptions.ValidationError):
        raise

    # Critical validation error - log and throw
    get_logger().exception(f"Error validating salary slip {getattr(doc, 'name', 'New')}: {e}")
    frappe.throw(_("Could not validate salary slip: {0}").format(str(e)))


def handle_submission_error(e: Exception, doc: SalarySlipDoc) -> None:
    """Handle exceptions during salary slip submission."""
    # Handle ValidationError separately
    if isinstance(e, frappe.exceptions.ValidationError):
        raise

    # Critical submission error - log and throw
    get_logger().exception(f"Error processing salary slip submission for {doc.name}: {e}")
    frappe.throw(_("Error processing salary slip submission: {0}").format(str(e)))


def handle_cancellation_error(e: Exception, doc: SalarySlipDoc) -> None:
    """Handle exceptions during salary slip cancellation."""
    # Handle ValidationError separately
    if isinstance(e, frappe.exceptions.ValidationError):
        raise

    # Critical cancellation error - log and throw
    get_logger().exception(f"Error processing salary slip cancellation for {doc.name}: {e}")
    frappe.throw(_("Error processing salary slip cancellation: {0}").format(str(e)))


def handle_post_creation_error(e: Exception, doc: SalarySlipDoc) -> None:
    """Handle exceptions during post-creation processing."""
    # Non-critical post-creation error - log and continue
    get_logger().warning(
        f"Error in post-creation processing for {getattr(doc, 'name', 'New')}: {e}"
    )
    frappe.msgprint(
        _("Warning: Error during post-creation processing: {0}").format(str(e)),
        indicator="orange",
    )
