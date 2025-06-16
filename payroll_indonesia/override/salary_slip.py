# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-23 03:38:05 by dannyaudian

from typing import Any, Dict, Optional, Union, List
import logging

import frappe
from frappe import _
from frappe.utils import flt, getdate, add_to_date, date_diff
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

# Import BPJS calculation module
from payroll_indonesia.override.salary_slip.bpjs_calculator import calculate_bpjs_components

# Import centralized tax calculation
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components

# Import standardized cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value

# Import constants
from payroll_indonesia.constants import (
    CACHE_MEDIUM,
    CACHE_LONG,
    MAX_DATE_DIFF,
    VALID_TAX_STATUS,
)

# Define exports for proper importing by other modules
__all__ = [
    "IndonesiaPayrollSalarySlip",
    "setup_fiscal_year_if_missing",
    "check_fiscal_year_setup",
    "extend_salary_slip_functionality",
]

# Type aliases
EmployeeDoc = Any  # frappe.model.document.Document type for Employee


def get_logger() -> logging.Logger:
    """Get properly configured logger for salary slip module."""
    return frappe.logger("salary_slip", with_more_info=True)


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Enhanced Salary Slip for Indonesian Payroll
    Extends hrms.payroll.doctype.salary_slip.salary_slip.SalarySlip

    Key features for Indonesian payroll:
    - BPJS calculations (Kesehatan, JHT, JP, JKK, JKM)
    - PPh 21 tax calculations with gross or gross-up methods
    - TER (Tarif Efektif Rata-rata) method support per PMK 168/PMK.010/2023
      - Implemented with 3 TER categories (TER A, TER B, TER C) based on PTKP
    - Integration with Employee Tax Summary
    """

    def validate(self) -> None:
        """
        Validate salary slip and calculate Indonesian components.
        Handles BPJS and tax calculations with appropriate error handling.
        """
        try:
            # Additional validations for Indonesian payroll
            self._validate_input_data()

            # Call parent validation after our validations
            super().validate()

            # Initialize additional fields
            self._initialize_payroll_fields()

            # Get employee document
            employee = self._get_employee_doc()

            # Additional validation for tax ID fields
            self._validate_tax_fields(employee)

            # Calculate BPJS components directly using the current salary slip
            calculate_bpjs_components(self)

            # Calculate tax components using centralized function
            calculate_tax_components(self, employee)

            # Final verifications
            self._verify_ter_settings()
            verify_bpjs_components(self)
            self._generate_tax_id_data(employee)
            self._check_or_create_fiscal_year()

            self.add_payroll_note("Validasi berhasil: Komponen BPJS dan Pajak dihitung.")

        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            # For other errors, log and re-raise
            get_logger().exception(f"Error validating salary slip for {self.employee}: {e}")
            frappe.throw(
                _("Error validating salary slip: {0}").format(str(e)), title=_("Validation Failed")
            )

    def _validate_input_data(self) -> None:
        """
        Validate basic input data for salary slip including:
        - Gross pay is non-negative
        - Posting date is within payroll entry range
        """
        # Validate gross pay is non-negative
        if hasattr(self, "gross_pay") and self.gross_pay < 0:
            frappe.throw(
                _("Gross pay cannot be negative. Current value: {0}").format(self.gross_pay),
                title=_("Invalid Gross Pay"),
            )

        # Validate posting date within payroll entry date range if linked to payroll entry
        if hasattr(self, "payroll_entry") and self.payroll_entry and hasattr(self, "posting_date"):
            try:
                payroll_entry_doc = frappe.get_doc("Payroll Entry", self.payroll_entry)
                start_date = getdate(payroll_entry_doc.start_date)
                end_date = getdate(payroll_entry_doc.end_date)
                posting_date = getdate(self.posting_date)

                # Check if posting date is within range
                if posting_date < start_date or posting_date > end_date:
                    frappe.throw(
                        _("Posting date {0} must be within payroll period {1} to {2}").format(
                            posting_date, start_date, end_date
                        ),
                        title=_("Invalid Posting Date"),
                    )

                # Check if the posting date is too far from the period
                days_diff = min(
                    date_diff(posting_date, start_date), date_diff(end_date, posting_date)
                )
                if days_diff > MAX_DATE_DIFF:  # Using constant instead of 31
                    frappe.throw(
                        _(
                            "Posting date {0} is too far from the payroll period ({1} to {2})"
                        ).format(posting_date, start_date, end_date),
                        title=_("Invalid Posting Date"),
                    )
            except Exception as e:
                if isinstance(e, frappe.exceptions.ValidationError):
                    raise

                get_logger().exception(f"Error validating posting date: {e}")
                frappe.throw(
                    _("Error validating posting date: {0}").format(str(e)),
                    title=_("Validation Error"),
                )

    def _validate_tax_fields(self, employee: EmployeeDoc) -> None:
        """
        Validate required tax fields when PPh 21 component is present:
        - NPWP (Tax ID) should be present
        - Status Pajak (Tax Status) should be set

        Args:
            employee: Employee document with tax fields
        """
        # Check if PPh 21 component exists in deductions
        has_pph21 = False
        if hasattr(self, "deductions"):
            for deduction in self.deductions:
                if deduction.salary_component == "PPh 21" and flt(deduction.amount) > 0:
                    has_pph21 = True
                    break

        # Only validate tax fields if PPh 21 is being calculated
        if has_pph21:
            # Validate NPWP exists
            npwp = getattr(self, "npwp", "") or getattr(employee, "npwp", "")
            if not npwp:
                frappe.throw(
                    _(
                        "NPWP (Tax ID) is required for PPh 21 calculation. Please update employee record."
                    ),
                    title=_("Missing NPWP"),
                )

            # Validate status_pajak (Tax Status) exists
            status_pajak = getattr(employee, "status_pajak", "")
            if not status_pajak:
                frappe.throw(
                    _(
                        "Tax status (Status Pajak) is required for PPh 21 calculation. Please update employee record."
                    ),
                    title=_("Missing Tax Status"),
                )

            # Check if status_pajak is valid
            if status_pajak not in VALID_TAX_STATUS:
                frappe.throw(
                    _("Invalid tax status: {0}. Should be one of: {1}").format(
                        status_pajak, ", ".join(VALID_TAX_STATUS)
                    ),
                    title=_("Invalid Tax Status"),
                )

    def _initialize_payroll_fields(self) -> Dict[str, Any]:
        """
        Initialize additional payroll fields with default values.
        Ensures all required fields exist with proper default values.

        Returns:
            Dict[str, Any]: Dictionary of default values used

        Raises:
            frappe.ValidationError: If field initialization fails
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
            }

            # Set defaults for fields that don't exist or are None
            for field, default in defaults.items():
                if not hasattr(self, field) or getattr(self, field) is None:
                    setattr(self, field, default)

            return defaults
        except Exception as e:
            # This is a critical initialization step - throw
            get_logger().exception(
                f"Error initializing payroll fields for "
                f"{self.name if hasattr(self, 'name') else 'New Salary Slip'}: {e}"
            )
            frappe.throw(
                _("Could not initialize payroll fields: {0}").format(str(e)),
                title=_("Field Initialization Error"),
            )

    def _get_employee_doc(self) -> EmployeeDoc:
        """
        Retrieves the complete Employee document for the current salary slip.
        Uses cache if available.

        Returns:
            Employee document with all fields

        Raises:
            frappe.ValidationError: If employee cannot be found or retrieved
        """
        if not hasattr(self, "employee") or not self.employee:
            frappe.throw(
                _("Salary Slip must have an employee assigned"), title=_("Missing Employee")
            )

        try:
            # Check cache first
            cache_key = f"employee_doc:{self.employee}"
            employee_doc = get_cached_value(cache_key)

            if employee_doc is None:
                employee_doc = frappe.get_doc("Employee", self.employee)
                # Cache for 1 hour
                cache_value(cache_key, employee_doc, CACHE_MEDIUM)

            return employee_doc
        except Exception as e:
            # Critical error - can't continue without employee
            get_logger().exception(
                f"Error retrieving employee {self.employee} for salary slip "
                f"{self.name if hasattr(self, 'name') else 'New'}: {e}"
            )
            frappe.throw(
                _("Could not retrieve Employee {0}: {1}").format(self.employee, str(e)),
                title=_("Employee Not Found"),
            )

    def _verify_ter_settings(self) -> None:
        """
        Verify TER settings are correctly applied if using TER method.
        Logs warnings for missing configuration.
        """
        try:
            if getattr(self, "is_using_ter", 0):
                # Verify TER category is set - warning only
                if not getattr(self, "ter_category", ""):
                    self.add_payroll_note("WARNING: Using TER but no category set")
                    frappe.msgprint(_("Warning: Using TER but no category set"), indicator="orange")

                # Verify TER rate is set - warning only
                if not getattr(self, "ter_rate", 0):
                    self.add_payroll_note("WARNING: Using TER but no rate set")
                    frappe.msgprint(_("Warning: Using TER but no rate set"), indicator="orange")
        except Exception as e:
            # Non-critical error - log and continue
            get_logger().warning(
                f"Error verifying TER settings for {self.name if hasattr(self, 'name') else 'New'}: {e}"
            )
            frappe.msgprint(_("Warning: Could not verify TER settings."), indicator="orange")

    def _generate_tax_id_data(self, employee: EmployeeDoc) -> None:
        """
        Extract and store tax-related IDs from the employee record.

        Args:
            employee: Employee document with tax identification
        """
        try:
            # Copy NPWP from employee if available
            if hasattr(employee, "npwp") and employee.npwp:
                self.npwp = employee.npwp
                self.db_set("npwp", employee.npwp, update_modified=False)

            # Copy KTP from employee if available
            if hasattr(employee, "ktp") and employee.ktp:
                self.ktp = employee.ktp
                self.db_set("ktp", employee.ktp, update_modified=False)
        except Exception as e:
            # Non-critical error - log and continue
            get_logger().warning(
                f"Error extracting tax IDs from employee {employee.name} for salary slip "
                f"{self.name if hasattr(self, 'name') else 'New'}: {e}"
            )
            frappe.msgprint(
                _("Warning: Could not retrieve tax identification from employee record."),
                indicator="orange",
            )

    def _check_or_create_fiscal_year(self) -> None:
        """
        Check if a fiscal year exists for the salary slip period
        and create one if missing.
        """
        try:
            if hasattr(self, "start_date"):
                cache_key = f"fiscal_year:{getdate(self.start_date)}"
                fiscal_year = get_cached_value(cache_key)

                if fiscal_year is None:
                    fiscal_year = check_fiscal_year_setup(self.start_date)
                    # Cache for 24 hours - fiscal years don't change often
                    cache_value(cache_key, fiscal_year, CACHE_LONG)

                if fiscal_year.get("status") == "error":
                    # Try to create fiscal year - non-critical operation
                    setup_result = setup_fiscal_year_if_missing(self.start_date)
                    self.add_payroll_note(
                        f"Fiscal year setup: {setup_result.get('status', 'unknown')}"
                    )
                    # Update cache with new fiscal year
                    cache_value(
                        cache_key,
                        {"status": "ok", "fiscal_year": setup_result.get("fiscal_year")},
                        CACHE_LONG,
                    )
        except Exception as e:
            # Non-critical error - log and continue
            get_logger().warning(
                f"Error checking or creating fiscal year for "
                f"{self.start_date if hasattr(self, 'start_date') else 'unknown date'}: {e}"
            )
            frappe.msgprint(
                _("Warning: Could not verify or create fiscal year."), indicator="orange"
            )

    def add_payroll_note(self, note: str, section: Optional[str] = None) -> None:
        """
        Add note to payroll_note field with optional section header.

        Args:
            note: Note text to add
            section: Optional section header for the note
        """
        try:
            if not hasattr(self, "payroll_note"):
                self.payroll_note = ""

            # Add section header if specified
            if section:
                formatted_note = f"\n\n=== {section} ===\n{note}"
            else:
                formatted_note = note

            # Add new note
            if self.payroll_note:
                self.payroll_note += f"\n{formatted_note}"
            else:
                self.payroll_note = formatted_note

            # Use db_set to avoid another full save
            self.db_set("payroll_note", self.payroll_note, update_modified=False)
        except Exception as e:
            # Non-critical error - log and continue
            get_logger().warning(
                f"Error adding payroll note to {self.name if hasattr(self, 'name') else 'New'}: {e}"
            )
            # No msgprint here since this is a background operation

    def on_submit(self) -> None:
        """
        Handle actions when salary slip is submitted.
        Updates related tax and benefit documents.
        """
        try:
            # Call parent handler first
            super().on_submit()

            # Verify TER settings before submit
            self._verify_ter_settings()

            # Verify BPJS components one last time
            verify_bpjs_components(self)

            # Create or update dependent documents
            self._update_tax_summary()
        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            # Critical error during submission - throw
            get_logger().exception(
                f"Error during salary slip submission for "
                f"{self.name if hasattr(self, 'name') else 'New'}: {e}"
            )
            frappe.throw(
                _("Error during salary slip submission: {0}").format(str(e)),
                title=_("Submission Failed"),
            )

    def _update_tax_summary(self) -> None:
        """
        Update or create employee tax summary document.
        This method enqueues a background job to update tax summary to prevent blocking UI.
        """
        try:
            # Don't update tax summary for unsubmitted salary slips
            if self.docstatus != 1:
                return

            # Use background job to update tax summary for better performance
            # This prevents the salary slip submission from being blocked by tax summary updates
            frappe.enqueue(
                method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.create_from_salary_slip",
                queue="long",
                timeout=600,
                salary_slip=self.name,
                is_async=True,
                job_name=f"tax_summary_update_{self.name}",
                now=False,  # Run in background
            )

            # Add note that tax summary update was queued
            self.add_payroll_note(
                f"Tax summary update queued in background job: tax_summary_update_{self.name}"
            )

        except Exception as e:
            # Non-critical error - log and continue
            # We don't want to block salary slip submission if tax summary fails
            get_logger().warning(f"Error queueing tax summary update for {self.name}: {e}")
            frappe.msgprint(
                _(
                    "Warning: Could not queue tax summary update. You may need to update it manually."
                ),
                indicator="orange",
            )

    def on_cancel(self) -> None:
        """
        Handle actions when salary slip is cancelled.
        Updates or reverts related documents.
        """
        try:
            # Call parent handler first
            super().on_cancel()

            # Update or revert dependent documents
            self._revert_tax_summary()
        except Exception as e:
            # Handle ValidationError separately
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            # Critical error during cancellation - throw
            get_logger().exception(f"Error during salary slip cancellation for {self.name}: {e}")
            frappe.throw(
                _("Error during salary slip cancellation: {0}").format(str(e)),
                title=_("Cancellation Failed"),
            )

    def _revert_tax_summary(self) -> None:
        """
        Revert changes to employee tax summary when salary slip is cancelled.
        This method enqueues a background job to revert tax summary to prevent blocking UI.
        """
        try:
            # Don't process for slips that were not submitted
            if self.docstatus != 2:  # 2 = Cancelled
                return

            # Use a background job to update tax summary
            year = getdate(self.end_date).year if hasattr(self, "end_date") else None

            if not year:
                self.add_payroll_note("Could not determine year for tax summary reversion")
                return

            frappe.enqueue(
                method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.update_on_salary_slip_cancel",
                queue="long",
                timeout=300,
                salary_slip=self.name,
                year=year,
                is_async=True,
                job_name=f"tax_summary_revert_{self.name}",
                now=False,  # Run in background
            )

            # Add note that tax summary reversion was queued
            self.add_payroll_note(
                f"Tax summary reversion queued in background job: tax_summary_revert_{self.name}"
            )

        except Exception as e:
            # Non-critical error - log and continue
            # We don't want to block salary slip cancellation if tax summary fails
            get_logger().warning(f"Error queueing tax summary reversion for {self.name}: {e}")
            frappe.msgprint(
                _(
                    "Warning: Could not queue tax summary reversion. You may need to update it manually."
                ),
                indicator="orange",
            )


def verify_bpjs_components(slip: Any) -> Dict[str, Any]:
    """
    Verify that BPJS components in the salary slip are correct.
    Updates custom fields from component rows if found.

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
                    title=_("BPJS Calculation Inconsistency"),
                )

            # Update to ensure consistency
            slip.total_bpjs = result["total"]
            slip.db_set("total_bpjs", result["total"], update_modified=False)

        # Log verification results
        log.debug(
            f"BPJS verification complete for {getattr(slip, 'name', 'unknown')}: "
            f"kesehatan={result['kesehatan_amount']}, jht={result['jht_amount']}, "
            f"jp={result['jp_amount']}, total={result['total']}"
        )

        return result

    except Exception as e:
        # Non-critical verification error - log and return default result
        log.exception(f"Error verifying BPJS components: {e}")
        frappe.msgprint(_("Warning: Could not verify BPJS components."), indicator="orange")
        # Return default result on error
        return result


# NEW APPROACH: Use hooks and monkey patching instead of full controller override
def extend_salary_slip_functionality() -> bool:
    """
    Safely extend SalarySlip functionality without replacing the entire controller.
    This approach uses selective monkey patching of specific methods while preserving
    the original controller class.

    Returns:
        bool: True if enhancement succeeded, False otherwise
    """
    try:
        # Get the original SalarySlip class
        original_class = frappe.get_doc_class("Salary Slip")

        # Dictionary mapping original methods to our enhanced methods
        method_mapping = {
            "validate": _enhance_validate,
            "on_submit": _enhance_on_submit,
            "on_cancel": _enhance_on_cancel,
            # Add any other methods you need to enhance
        }

        # Apply the enhancements
        for method_name, enhancement_func in method_mapping.items():
            if hasattr(original_class, method_name):
                original_method = getattr(original_class, method_name)
                enhanced_method = _create_enhanced_method(original_method, enhancement_func)
                setattr(original_class, method_name, enhanced_method)

        # Log successful enhancement
        get_logger().info(
            "Successfully enhanced SalarySlip controller with Indonesian payroll features"
        )

        return True
    except Exception as e:
        # Non-critical error with monkey patching - log but don't throw
        get_logger().exception(f"Error enhancing SalarySlip controller: {e}")
        frappe.msgprint(
            _(
                "Warning: Could not enhance SalarySlip controller. Some Indonesian payroll features may not be available."
            ),
            indicator="red",
        )
        return False


def _create_enhanced_method(original_method: Any, enhancement_func: Any) -> Any:
    """
    Creates an enhanced method that calls the original method and then applies
    our enhancement function.

    Args:
        original_method: The original class method
        enhancement_func: Our enhancement function that will be called after the original

    Returns:
        A new function that combines both behaviors
    """

    def enhanced_method(self, *args, **kwargs):
        # First apply our additional validations if this is the validate method
        if original_method.__name__ == "validate":
            _validate_input_data_standalone(self)
            employee = _get_employee_doc_standalone(self)
            if employee:
                _validate_tax_fields_standalone(self, employee)

        # Call the original method
        result = original_method(self, *args, **kwargs)

        # Then apply our enhancement
        try:
            enhancement_func(self, *args, **kwargs)
        except Exception as e:
            # Log error but don't break the original functionality
            get_logger().exception(
                f"Error in enhancement for {self.name if hasattr(self, 'name') else 'New Document'}: {e}"
            )
            frappe.msgprint(
                _("Warning: Error in salary slip enhancement: {0}").format(str(e)),
                indicator="orange",
            )

        # Return the original result
        return result

    # Copy the original method's docstring and attributes
    if hasattr(original_method, "__doc__"):
        enhanced_method.__doc__ = original_method.__doc__

    # Add a note that this is an enhanced version
    if enhanced_method.__doc__:
        enhanced_method.__doc__ += "\n\nEnhanced with Indonesian payroll features."
    else:
        enhanced_method.__doc__ = "Enhanced with Indonesian payroll features."

    return enhanced_method


# Standalone validation functions for use with enhanced methods
def _validate_input_data_standalone(doc: Any) -> None:
    """
    Validate basic input data for salary slip including:
    - Gross pay is non-negative
    - Posting date is within payroll entry range

    For use with the enhanced validate method.
    """
    # Validate gross pay is non-negative
    if hasattr(doc, "gross_pay") and doc.gross_pay < 0:
        frappe.throw(
            _("Gross pay cannot be negative. Current value: {0}").format(doc.gross_pay),
            title=_("Invalid Gross Pay"),
        )

    # Validate posting date within payroll entry date range if linked to payroll entry
    if hasattr(doc, "payroll_entry") and doc.payroll_entry and hasattr(doc, "posting_date"):
        try:
            payroll_entry_doc = frappe.get_doc("Payroll Entry", doc.payroll_entry)
            start_date = getdate(payroll_entry_doc.start_date)
            end_date = getdate(payroll_entry_doc.end_date)
            posting_date = getdate(doc.posting_date)

            # Check if posting date is within range
            if posting_date < start_date or posting_date > end_date:
                frappe.throw(
                    _("Posting date {0} must be within payroll period {1} to {2}").format(
                        posting_date, start_date, end_date
                    ),
                    title=_("Invalid Posting Date"),
                )

            # Check if the posting date is too far from the period
            days_diff = min(date_diff(posting_date, start_date), date_diff(end_date, posting_date))
            if days_diff > MAX_DATE_DIFF:
                frappe.throw(
                    _("Posting date {0} is too far from the payroll period ({1} to {2})").format(
                        posting_date, start_date, end_date
                    ),
                    title=_("Invalid Posting Date"),
                )
        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise

            get_logger().exception(f"Error validating posting date: {e}")
            frappe.throw(
                _("Error validating posting date: {0}").format(str(e)), title=_("Validation Error")
            )


def _get_employee_doc_standalone(doc: Any) -> Optional[Any]:
    """
    Get employee document for standalone validation.

    Returns:
        The employee document or None if not found
    """
    if hasattr(doc, "employee") and doc.employee:
        try:
            # Check cache first
            cache_key = f"employee_doc:{doc.employee}"
            employee_doc = get_cached_value(cache_key)

            if employee_doc is None:
                employee_doc = frappe.get_doc("Employee", doc.employee)
                # Cache for 1 hour
                cache_value(cache_key, employee_doc, CACHE_MEDIUM)

            return employee_doc
        except Exception as e:
            get_logger().warning(
                f"Error retrieving employee {doc.employee} for standalone validation: {e}"
            )
    return None


def _validate_tax_fields_standalone(doc: Any, employee: Any) -> None:
    """
    Validate required tax fields when PPh 21 component is present:
    - NPWP (Tax ID) should be present
    - Status Pajak (Tax Status) should be set

    For use with the enhanced validate method.
    """
    # Check if PPh 21 component exists in deductions
    has_pph21 = False
    if hasattr(doc, "deductions"):
        for deduction in doc.deductions:
            if deduction.salary_component == "PPh 21" and flt(deduction.amount) > 0:
                has_pph21 = True
                break

    # Only validate tax fields if PPh 21 is being calculated
    if has_pph21:
        # Validate NPWP exists
        npwp = getattr(doc, "npwp", "") or getattr(employee, "npwp", "")
        if not npwp:
            frappe.throw(
                _(
                    "NPWP (Tax ID) is required for PPh 21 calculation. Please update employee record."
                ),
                title=_("Missing NPWP"),
            )

        # Validate status_pajak (Tax Status) exists
        status_pajak = getattr(employee, "status_pajak", "")
        if not status_pajak:
            frappe.throw(
                _(
                    "Tax status (Status Pajak) is required for PPh 21 calculation. Please update employee record."
                ),
                title=_("Missing Tax Status"),
            )

        # Check if status_pajak is valid
        if status_pajak not in VALID_TAX_STATUS:
            frappe.throw(
                _("Invalid tax status: {0}. Should be one of: {1}").format(
                    status_pajak, ", ".join(VALID_TAX_STATUS)
                ),
                title=_("Invalid Tax Status"),
            )


def _initialize_payroll_fields_standalone(doc: Any) -> Dict[str, Any]:
    """
    Initialize additional payroll fields with default values for standalone use.

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
        }

        # Set defaults for fields that don't exist or are None
        for field, default in defaults.items():
            if not hasattr(doc, field) or getattr(doc, field) is None:
                setattr(doc, field, default)
                try:
                    # Try to use db_set for persistence
                    doc.db_set(field, default, update_modified=False)
                except Exception:
                    pass  # Ignore errors in db_set for non-critical fields

        return defaults
    except Exception as e:
        get_logger().warning(f"Error initializing payroll fields: {e}")
        return {}


def _enhance_validate(doc: Any, *args, **kwargs) -> None:
    """
    Enhancement function for the validate method.
    This will be called after the original validate method.

    Args:
        doc: The Salary Slip document
    """
    try:
        # Only proceed for the correct doctype
        if doc.doctype != "Salary Slip":
            return

        # Create a temporary IndonesiaPayrollSalarySlip to use its methods
        temp = IndonesiaPayrollSalarySlip(doc.as_dict())

        # Initialize additional fields
        temp._initialize_payroll_fields()

        # Get employee document using cache
        cache_key = f"employee_doc:{doc.employee}"
        employee = get_cached_value(cache_key)

        if employee is None:
            employee = temp._get_employee_doc()
            # Cache already handled in _get_employee_doc()

        # Calculate BPJS components directly using original doc
        calculate_bpjs_components(doc)

        # Calculate tax components using centralized function
        calculate_tax_components(doc, employee)

        # Verify BPJS components
        verify_bpjs_components(doc)

        # Copy back all the fields that were calculated for persistence
        fields_to_update = [
            "biaya_jabatan",
            "netto",
            "total_bpjs",
            "kesehatan_employee",
            "jht_employee",
            "jp_employee",
            "is_using_ter",
            "ter_rate",
            "ter_category",
            "koreksi_pph21",
            "payroll_note",
            "npwp",
            "ktp",
            "is_final_gabung_suami",
        ]

        # Update each field using both attribute and db_set if possible
        for field in fields_to_update:
            if hasattr(doc, field):
                try:
                    # Use db_set for immediate persistence
                    doc.db_set(field, getattr(doc, field), update_modified=False)
                except Exception:
                    # Ignore db_set errors
                    pass

        # Add note about successful validation
        if hasattr(doc, "payroll_note"):
            note = "Validasi berhasil: Komponen BPJS dan Pajak dihitung."
            if doc.payroll_note:
                if note not in doc.payroll_note:
                    doc.payroll_note += f"\n{note}"
            else:
                doc.payroll_note = note
            try:
                doc.db_set("payroll_note", doc.payroll_note, update_modified=False)
            except Exception:
                pass

    except Exception as e:
        # Non-critical error in enhancement - log and continue
        get_logger().exception(
            f"Error in _enhance_validate for "
            f"{doc.name if hasattr(doc, 'name') else 'New Salary Slip'}: {e}"
        )
        frappe.msgprint(
            _(
                "Warning: Error enhancing salary slip validation. Some features may not be available."
            ),
            indicator="orange",
        )


def _enhance_on_submit(doc: Any, *args, **kwargs) -> None:
    """
    Enhancement function for the on_submit method.
    This will be called after the original on_submit method.

    Args:
        doc: The Salary Slip document
    """
    try:
        # Only proceed for the correct doctype
        if doc.doctype != "Salary Slip":
            return

        # Verify BPJS components are correct before final submission
        verify_bpjs_components(doc)

        # Update tax summary in background job
        _enqueue_tax_summary_update(doc)

    except Exception as e:
        # Non-critical error in enhancement - log and continue
        get_logger().warning(f"Error in _enhance_on_submit for {doc.name}: {e}")
        frappe.msgprint(
            _(
                "Warning: Error enhancing salary slip submission. Some features may not be available."
            ),
            indicator="orange",
        )


def _enhance_on_cancel(doc: Any, *args, **kwargs) -> None:
    """
    Enhancement function for the on_cancel method.
    This will be called after the original on_cancel method.

    Args:
        doc: The Salary Slip document
    """
    try:
        # Only proceed for the correct doctype
        if doc.doctype != "Salary Slip":
            return

        # Revert tax summary in background job
        _enqueue_tax_summary_revert(doc)

    except Exception as e:
        # Non-critical error in enhancement - log and continue
        get_logger().warning(f"Error in _enhance_on_cancel for {doc.name}: {e}")
        frappe.msgprint(
            _(
                "Warning: Error enhancing salary slip cancellation. Some features may not be available."
            ),
            indicator="orange",
        )


def _enqueue_tax_summary_update(doc: Any) -> None:
    """
    Enqueue a background job to update the tax summary.
    Separate function for reusability.

    Args:
        doc: Salary Slip document
    """
    try:
        # Don't update for unsubmitted documents
        if not hasattr(doc, "docstatus") or doc.docstatus != 1:
            return

        # Queue background job
        frappe.enqueue(
            method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.create_from_salary_slip",
            queue="long",
            timeout=600,
            salary_slip=doc.name,
            is_async=True,
            job_name=f"tax_summary_update_{doc.name}",
            now=False,
        )

        # Add note about job
        if hasattr(doc, "add_payroll_note"):
            doc.add_payroll_note(
                f"Tax summary update queued in background job: tax_summary_update_{doc.name}"
            )

    except Exception as e:
        get_logger().warning(f"Error queueing tax summary update for {doc.name}: {e}")
        frappe.msgprint(_("Warning: Could not queue tax summary update."), indicator="orange")


def _enqueue_tax_summary_revert(doc: Any) -> None:
    """
    Enqueue a background job to revert the tax summary.
    Separate function for reusability.

    Args:
        doc: Salary Slip document
    """
    try:
        # Don't revert for non-cancelled documents
        if not hasattr(doc, "docstatus") or doc.docstatus != 2:
            return

        # Determine tax year
        year = None
        if hasattr(doc, "end_date") and doc.end_date:
            year = getdate(doc.end_date).year

        if not year:
            get_logger().warning(f"Could not determine year for tax summary reversion: {doc.name}")
            return

        # Queue background job
        frappe.enqueue(
            method="payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.update_on_salary_slip_cancel",
            queue="long",
            timeout=300,
            salary_slip=doc.name,
            year=year,
            is_async=True,
            job_name=f"tax_summary_revert_{doc.name}",
            now=False,
        )

        # Add note about job
        if hasattr(doc, "add_payroll_note"):
            doc.add_payroll_note(
                f"Tax summary reversion queued in background job: tax_summary_revert_{doc.name}"
            )

    except Exception as e:
        get_logger().warning(f"Error queueing tax summary reversion for {doc.name}: {e}")
        frappe.msgprint(_("Warning: Could not queue tax summary reversion."), indicator="orange")


# Helper function for fiscal year management
def check_fiscal_year_setup(date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Check if fiscal years are properly set up for a given date.

    Args:
        date_str: Date string to check fiscal year for. Uses current date if not provided.

    Returns:
        Dict[str, Any]: Status and message regarding fiscal year setup
    """
    try:
        test_date = getdate(date_str) if date_str else getdate()

        # Use cache for fiscal year lookup
        cache_key = f"fiscal_year_check:{test_date}"
        cached_result = get_cached_value(cache_key)

        if cached_result is not None:
            return cached_result

        fiscal_year = frappe.db.get_value(
            "Fiscal Year",
            {"year_start_date": ["<=", test_date], "year_end_date": [">=", test_date]},
        )

        if not fiscal_year:
            result = {
                "status": "error",
                "message": f"No active Fiscal Year found for date {test_date}",
                "solution": "Create a Fiscal Year that includes this date in Company settings",
            }
            # Cache negative result for 1 hour
            cache_value(cache_key, result, CACHE_MEDIUM)
            return result

        result = {"status": "ok", "fiscal_year": fiscal_year}
        # Cache positive result for 24 hours
        cache_value(cache_key, result, CACHE_LONG)
        return result
    except Exception as e:
        # Non-critical error - return error status
        get_logger().exception(
            f"Error checking fiscal year setup for date {date_str if date_str else 'current date'}: {e}"
        )
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def setup_fiscal_year_if_missing(date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Automatically set up a fiscal year if missing for a given date.

    Args:
        date_str: Date string to create fiscal year for. Uses current date if not provided.

    Returns:
        Dict[str, Any]: Status and details of the fiscal year setup operation
    """
    try:
        test_date = getdate(date_str) if date_str else getdate()

        # Check cache first
        cache_key = f"fiscal_year_setup:{test_date}"
        cached_result = get_cached_value(cache_key)

        if cached_result is not None:
            return cached_result

        # Check if fiscal year exists
        fiscal_year = frappe.db.get_value(
            "Fiscal Year",
            {"year_start_date": ["<=", test_date], "year_end_date": [">=", test_date]},
        )

        if fiscal_year:
            result = {"status": "exists", "fiscal_year": fiscal_year}
            # Cache result for 24 hours
            cache_value(cache_key, result, CACHE_LONG)
            return result

        # Create a new fiscal year
        year = test_date.year
        fy_start_month = frappe.db.get_single_value("Accounts Settings", "fy_start_date_is") or 1

        # Create fiscal year based on start month
        if fy_start_month == 1:
            # Calendar year
            start_date = getdate(f"{year}-01-01")
            end_date = getdate(f"{year}-12-31")
        else:
            # Custom fiscal year
            start_date = getdate(f"{year}-{fy_start_month:02d}-01")
            if start_date > test_date:
                start_date = add_to_date(start_date, years=-1)
            end_date = add_to_date(start_date, days=-1, years=1)

        # Create the fiscal year
        new_fy = frappe.new_doc("Fiscal Year")
        new_fy.year = f"{start_date.year}"
        if start_date.year != end_date.year:
            new_fy.year += f"-{end_date.year}"
        new_fy.year_start_date = start_date
        new_fy.year_end_date = end_date
        new_fy.save()

        result = {
            "status": "created",
            "fiscal_year": new_fy.name,
            "year": new_fy.year,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        }

        # Cache result for 24 hours
        cache_value(cache_key, result, CACHE_LONG)
        return result

    except Exception as e:
        # This is a critical operation for payroll - throw if user invoked
        # but just return error if called programmatically
        get_logger().exception(f"Error setting up fiscal year: {e}")
        if (
            frappe.local.form_dict.cmd
            == "payroll_indonesia.override.salary_slip.setup_fiscal_year_if_missing"
        ):
            frappe.throw(
                _("Failed to set up fiscal year: {0}").format(str(e)),
                title=_("Fiscal Year Setup Failed"),
            )
        return {"status": "error", "message": str(e)}


# Utility functions for bulk tax summary operations
@frappe.whitelist()
def refresh_multiple_tax_summaries(
    salary_slips: Union[List[str], str], is_async: bool = True
) -> Dict[str, Any]:
    """
    Refresh tax summaries for multiple salary slips.

    Args:
        salary_slips: List of salary slip names or JSON string with list
        is_async: Whether to process in background jobs (recommended for performance)

    Returns:
        Dict[str, Any]: Status and details of the operation
    """
    try:
        # Handle JSON string input
        if isinstance(salary_slips, str):
            import json

            try:
                salary_slips = json.loads(salary_slips)
            except ValueError:
                # If it's not valid JSON, treat it as a single slip
                salary_slips = [salary_slips]

        if not salary_slips:
            return {"status": "error", "message": "No salary slips provided"}

        # Validate list type
        if not isinstance(salary_slips, list):
            return {"status": "error", "message": "Invalid salary slip data provided"}

        # Log the operation
        get_logger().info(f"Starting refresh of tax summaries for {len(salary_slips)} salary slips")

        if is_async:
            # Use background processing for better performance
            batch_size = 20  # Process in batches of 20 for better performance
            for i in range(0, len(salary_slips), batch_size):
                batch = salary_slips[i : i + batch_size]

                # Queue a job for each batch
                frappe.enqueue(
                    method="_process_tax_summary_batch",
                    queue="long",
                    timeout=1800,  # 30 minutes timeout for large batches
                    slips=batch,
                    job_name=f"tax_summary_batch_{i}_{i+len(batch)}",
                    now=False,
                )

            return {
                "status": "queued",
                "message": f"Queued {len(salary_slips)} salary slips for tax summary refresh",
                "total_slips": len(salary_slips),
                "batch_size": batch_size,
                "batches": (len(salary_slips) + batch_size - 1) // batch_size,
            }
        else:
            # Process synchronously (not recommended for many slips)
            results = _process_tax_summary_batch(salary_slips)
            return {
                "status": "completed",
                "message": f"Processed {len(salary_slips)} salary slips",
                "results": results,
            }

    except Exception as e:
        get_logger().exception(f"Error refreshing multiple tax summaries: {e}")
        return {"status": "error", "message": str(e)}


def _process_tax_summary_batch(slips: List[str]) -> Dict[str, Any]:
    """
    Process a batch of salary slips to refresh tax summaries.

    Args:
        slips: List of salary slip document names

    Returns:
        Dict[str, Any]: Results of processing
    """
    results = {"processed": 0, "success": 0, "failed": 0, "errors": []}

    for slip_name in slips:
        try:
            # Get the salary slip
            slip = frappe.get_doc("Salary Slip", slip_name)

            # Only process submitted slips
            if slip.docstatus != 1:
                results["errors"].append({"slip": slip_name, "error": "Slip is not submitted"})
                results["failed"] += 1
                continue

            # Process tax summary update
            # No need to get the tax summary name since we're not using it
            # Just create or update tax summary directly
            from payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary import (
                create_from_salary_slip,
            )

            create_from_salary_slip(slip_name)

            results["success"] += 1

        except Exception as e:
            results["errors"].append({"slip": slip_name, "error": str(e)})
            results["failed"] += 1

        finally:
            results["processed"] += 1

    return results


# Hook to apply our extensions when the module is loaded
def setup_hooks() -> None:
    """Set up our hooks and monkey patches when the module is loaded"""
    try:
        extend_salary_slip_functionality()
    except Exception as e:
        # Non-critical error during setup - log but continue
        get_logger().exception(f"Error setting up hooks for salary slip: {e}")


# Apply extensions
setup_hooks()
