# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from typing import Any, Dict, Optional, List
import logging

import frappe
from frappe import _
from frappe.utils import flt, getdate
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value
from payroll_indonesia.constants import CACHE_MEDIUM, CACHE_LONG, VALID_TAX_STATUS

__all__ = ["IndonesiaPayrollSalarySlip", "setup_fiscal_year_if_missing"]


def get_logger() -> logging.Logger:
    """Get properly configured logger for salary slip module."""
    return frappe.logger("salary_slip", with_more_info=True)


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Enhanced Salary Slip for Indonesian Payroll, supporting BPJS and PPh 21 tax
    calculations, with multi-company support and TER methodology.
    """

    def validate(self) -> None:
        """Validate salary slip and calculate Indonesian tax/BPJS components."""
        try:
            # Sync December flag with Payroll Entry
            self._sync_december_flag()
            
            # Additional validations for Indonesian payroll
            self._validate_input_data()

            # Call parent validation
            super().validate()

            # Initialize additional fields
            self._initialize_payroll_fields()

            # Get employee document
            employee = self._get_employee_doc()

            # Additional validation for tax ID fields
            self._validate_tax_fields(employee)

            # Process BPJS components
            self._process_bpjs_components()
            
            # Calculate YTD values
            self._calculate_ytd_values()

            # Process tax components
            self._process_tax_components(employee)

            # Final verifications
            self._verify_all_components()

            self.add_payroll_note("Validation successful: BPJS and tax components calculated.")

        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
            get_logger().exception(f"Error validating salary slip for {self.employee}: {e}")
            frappe.throw(_("Error validating salary slip: {0}").format(str(e)))

    def _sync_december_flag(self) -> None:
        """Sync December override flag with Payroll Entry if linked."""
        from payroll_indonesia.override.salary_slip_functions import _sync_december_flag_standalone
        _sync_december_flag_standalone(self)

    def _validate_input_data(self) -> None:
        """Validate basic input data including gross pay and posting date."""
        from payroll_indonesia.override.salary_slip_functions import _validate_input_data_standalone
        _validate_input_data_standalone(self)

    def _initialize_payroll_fields(self) -> None:
        """Initialize additional fields required for Indonesian payroll."""
        from payroll_indonesia.override.salary_slip_functions import _initialize_payroll_fields
        _initialize_payroll_fields(self)

    def _get_employee_doc(self) -> Any:
        """Get employee document with efficient caching."""
        if not hasattr(self, "employee") or not self.employee:
            frappe.throw(_("Employee is required"), title=_("Missing Employee"))

        try:
            cache_key = f"employee_doc:{self.employee}"
            employee_doc = get_cached_value(cache_key)

            if employee_doc is None:
                employee_doc = frappe.get_doc("Employee", self.employee)
                cache_value(cache_key, employee_doc, CACHE_MEDIUM)

            return employee_doc
        except Exception as e:
            get_logger().exception(f"Error retrieving employee {self.employee}: {e}")
            frappe.throw(_("Could not retrieve Employee: {0}").format(str(e)))

    def _validate_tax_fields(self, employee: Any) -> None:
        """Validate tax fields when PPh 21 component is present."""
        # Check if PPh 21 component exists
        has_pph21 = False
        if hasattr(self, "deductions"):
            for deduction in self.deductions:
                if deduction.salary_component == "PPh 21" and flt(deduction.amount) > 0:
                    has_pph21 = True
                    break

        if has_pph21:
            # Validate NPWP exists
            npwp = getattr(self, "npwp", "") or getattr(employee, "npwp", "")
            if not npwp:
                frappe.throw(_("NPWP is required for tax calculation"))

            # Validate tax status exists and is valid
            status_pajak = getattr(employee, "status_pajak", "")
            if not status_pajak:
                frappe.throw(_("Tax status is required for tax calculation"))
            
            if status_pajak not in VALID_TAX_STATUS:
                frappe.throw(
                    _("Invalid tax status: {0}. Should be one of: {1}").format(
                        status_pajak, ", ".join(VALID_TAX_STATUS)
                    )
                )

    def _process_bpjs_components(self) -> None:
        """Calculate BPJS components using centralized calculator."""
        from payroll_indonesia.override.salary_slip.bpjs_calculator import (
            calculate_bpjs_components
        )
        calculate_bpjs_components(self)
        
        # Calculate total BPJS deductions
        self._calculate_total_bpjs()

    def _calculate_total_bpjs(self) -> None:
        """Calculate and store total BPJS deductions."""
        bpjs_total = 0
        
        if hasattr(self, "deductions") and self.deductions:
            for deduction in self.deductions:
                component_name = deduction.salary_component
                if any(bpjs_type in component_name for bpjs_type in 
                      ["BPJS Kesehatan", "BPJS JHT", "BPJS JP"]):
                    bpjs_total += flt(deduction.amount)
        
        self.bpjs_deductions = bpjs_total
        
        if hasattr(self, "name") and self.name:
            try:
                self.db_set("bpjs_deductions", bpjs_total, update_modified=False)
            except Exception as e:
                get_logger().warning(f"Error saving BPJS deductions: {e}")

    def _calculate_ytd_values(self) -> None:
        """Calculate YTD values for gross pay and BPJS deductions."""
        from payroll_indonesia.payroll_indonesia.salary_slip import calculate_ytd_and_ytm
        
        ytd_vals = calculate_ytd_and_ytm(self)
        self.ytd_gross_pay = ytd_vals["ytd_gross"]
        self.ytd_bpjs_deductions = ytd_vals["ytd_bpjs"]
        
        if hasattr(self, "name") and self.name:
            try:
                self.db_set("ytd_gross_pay", self.ytd_gross_pay, update_modified=False)
                self.db_set("ytd_bpjs_deductions", self.ytd_bpjs_deductions, 
                           update_modified=False)
            except Exception as e:
                get_logger().warning(f"Error saving YTD values: {e}")
                self.add_payroll_note(f"Warning: Could not save YTD values: {str(e)}")

    def _process_tax_components(self, employee: Any) -> None:
        """Calculate tax components using centralized tax calculator."""
        from payroll_indonesia.override.salary_slip.tax_calculator import (
            calculate_tax_components
        )
        calculate_tax_components(self, employee)

    def _verify_all_components(self) -> None:
        """Perform final verification of all calculated components."""
        from payroll_indonesia.override.salary_slip_functions import (
            _verify_ter_settings, verify_bpjs_components
        )
        
        # Verify TER settings
        _verify_ter_settings(self)
        
        # Verify BPJS components
        verify_bpjs_components(self)
        
        # Generate tax ID data
        self._generate_tax_id_data()
        
        # Check fiscal year
        self._check_fiscal_year()

    def _generate_tax_id_data(self) -> None:
        """Copy tax IDs from employee record if available."""
        try:
            employee = self._get_employee_doc()
            
            if hasattr(employee, "npwp") and employee.npwp:
                self.npwp = employee.npwp
                self.db_set("npwp", employee.npwp, update_modified=False)

            if hasattr(employee, "ktp") and employee.ktp:
                self.ktp = employee.ktp
                self.db_set("ktp", employee.ktp, update_modified=False)
        except Exception as e:
            get_logger().warning(f"Error extracting tax IDs: {e}")
            frappe.msgprint(_("Warning: Could not extract tax IDs"), indicator="orange")

    def _check_fiscal_year(self) -> None:
        """Check and create fiscal year if missing."""
        try:
            if hasattr(self, "start_date"):
                from payroll_indonesia.payroll_indonesia.salary_slip import (
                    check_fiscal_year_setup, setup_fiscal_year_if_missing
                )
                
                fiscal_year = check_fiscal_year_setup(self.start_date)
                
                if fiscal_year.get("status") == "error":
                    setup_result = setup_fiscal_year_if_missing(self.start_date)
                    self.add_payroll_note(
                        f"Fiscal year setup: {setup_result.get('status', 'unknown')}"
                    )
        except Exception as e:
            get_logger().warning(f"Error checking fiscal year: {e}")
            frappe.msgprint(_("Warning: Could not verify fiscal year"), indicator="orange")

    def add_payroll_note(self, note: str, section: Optional[str] = None) -> None:
        """Add a note to the payroll_note field with optional section header."""
        try:
            if not hasattr(self, "payroll_note"):
                self.payroll_note = ""

            if section:
                formatted_note = f"\n\n=== {section} ===\n{note}"
            else:
                formatted_note = note

            if self.payroll_note:
                self.payroll_note += f"\n{formatted_note}"
            else:
                self.payroll_note = formatted_note

            self.db_set("payroll_note", self.payroll_note, update_modified=False)
        except Exception as e:
            get_logger().warning(f"Error adding payroll note: {e}")

    def on_submit(self) -> None:
        """Handle submission actions including tax summary updates."""
        try:
            # Call parent handler
            super().on_submit()

            # Final verification before submit
            self._verify_all_components()

            # Update tax summary if needed
            self._update_tax_summary()
        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
            get_logger().exception(f"Error during salary slip submission: {e}")
            frappe.throw(_("Error during submission: {0}").format(str(e)))

    def _update_tax_summary(self) -> None:
        """Enqueue tax summary update in background job."""
        if self.docstatus != 1:
            return

        from payroll_indonesia.override.salary_slip_functions import _enqueue_tax_summary_update
        _enqueue_tax_summary_update(self)

    def on_cancel(self) -> None:
        """Handle cancellation actions including tax summary reversion."""
        try:
            # Call parent handler
            super().on_cancel()

            # Revert tax summary
            self._revert_tax_summary()
        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
            get_logger().exception(f"Error during salary slip cancellation: {e}")
            frappe.throw(_("Error during cancellation: {0}").format(str(e)))

    def _revert_tax_summary(self) -> None:
        """Enqueue tax summary reversion in background job."""
        if self.docstatus != 2:  # 2 = Cancelled
            return

        from payroll_indonesia.override.salary_slip_functions import (
            _get_tax_year_from_slip, _enqueue_tax_summary_reversion
        )
        
        year = _get_tax_year_from_slip(self)
        if year:
            _enqueue_tax_summary_reversion(self, year)
        else:
            self.add_payroll_note("Could not determine year for tax summary reversion")


def setup_fiscal_year_if_missing(date_str: Optional[str] = None) -> Dict[str, Any]:
    """Create fiscal year if missing for the given date."""
    from payroll_indonesia.payroll_indonesia.utils import setup_fiscal_year_if_missing as setup_fy
    return setup_fy(date_str)


def calculate_ytd_and_ytm(slip: Any, date: Optional[str] = None) -> Dict[str, float]:
    """Calculate YTD and YTM values for salary slip components."""
    from payroll_indonesia.override.salary_slip_functions import calculate_ytd_and_ytm as calc_ytd
    return calc_ytd(slip, date)


def apply_hooks() -> None:
    """Apply hooks to extend standard Salary Slip functionality."""
    try:
        from payroll_indonesia.override.salary_slip_functions import extend_salary_slip_functionality
        extend_salary_slip_functionality()
    except Exception as e:
        get_logger().exception(f"Error applying salary slip hooks: {e}")
        frappe.msgprint(
            _("Warning: Could not apply salary slip hooks. Some features may be unavailable."),
            indicator="red"
        )


# Apply hooks when module is loaded
apply_hooks()
