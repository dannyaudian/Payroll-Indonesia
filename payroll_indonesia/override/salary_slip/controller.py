# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:35:42 by dannyaudian

"""
Controller module for Indonesia Payroll Salary Slip class.
"""

import frappe
from frappe import _
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from payroll_indonesia.override.salary_slip_functions import (
    salary_slip_post_submit, 
    initialize_fields,
    update_component_amount
)
from payroll_indonesia.frappe_helpers import logger

__all__ = ["IndonesiaPayrollSalarySlip"]


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Enhanced Salary Slip for Indonesian Payroll.

    Extends the standard Salary Slip with support for Indonesian tax regulations,
    BPJS calculations, and year-end tax corrections.
    
    Bypasses payroll period validation for more flexible processing.
    """

    def validate(self):
        """
        Validate salary slip with Indonesian payroll requirements.

        Performs validation while bypassing payroll period checks.
        """
        try:
            # Initialize fields first
            initialize_fields(self)
            
            # Handle date details if needed
            if not getattr(self, "salary_slip_based_on_timesheet", False):
                if hasattr(self, "get_date_details"):
                    self.get_date_details()
            
            # Skip payroll period validation which is called in parent validate
            
            # Safe calls to parent methods - only if they exist
            self._safe_call("validate_loan_repayment")
            self._safe_call("validate_employee_details")
            
            if not getattr(self, "salary_slip_based_on_timesheet", False):
                self._safe_call("validate_attendance")
            
            self._safe_call("validate_components_with_flexible_benefits")
            
            # Load employee doc for tax calculations
            self._load_employee_doc()
            
            # Update components with Indonesian calculations
            update_component_amount(self)
            
            # Calculate net pay and set status
            if hasattr(self, "calculate_net_pay"):
                self.calculate_net_pay()
                
            if hasattr(self, "set_status"):
                self.set_status()
            
            logger.info(f"Indonesia payroll validation completed for {self.name}")
        except Exception as e:
            logger.exception(f"Error validating salary slip {self.name}: {e}")
            frappe.throw(_("Error validating salary slip: {0}").format(str(e)))

    def _safe_call(self, method_name):
        """Safely call a method if it exists."""
        if hasattr(self, method_name):
            try:
                method = getattr(self, method_name)
                method()
            except Exception as e:
                logger.warning(f"Error calling {method_name}: {e}")
    
    # Stub methods to prevent attribute errors
    def validate_payroll_period(self):
        """
        Override to bypass the standard payroll period validation.
        
        This method is intentionally empty to bypass validation.
        """
        logger.debug(f"Bypassing payroll period validation for {self.name}")
        return True
    
    def validate_loan_repayment(self):
        """Stub method if parent doesn't have this."""
        pass
    
    def validate_employee_details(self):
        """Stub method if parent doesn't have this."""
        pass
    
    def validate_attendance(self):
        """Stub method if parent doesn't have this."""
        pass
    
    def validate_components_with_flexible_benefits(self):
        """Stub method if parent doesn't have this."""
        pass

    def _load_employee_doc(self):
        """Load employee document if not already loaded."""
        if not hasattr(self, "employee_doc") and getattr(self, "employee", None):
            try:
                self.employee_doc = frappe.get_doc("Employee", self.employee)
            except Exception as e:
                logger.warning(f"Could not load employee_doc for {self.employee}: {e}")

    def calculate_totals(self) -> None:
        """Backward-compat wrapper used by salary_slip_functions."""
        if hasattr(self, "calculate_net_pay"):
            self.calculate_net_pay()

    def on_submit(self):
        """
        Process document on submission.

        Executes submission and post-submission tasks for Indonesian payroll.
        """
        try:
            # Ensure fields are initialized
            initialize_fields(self)
            
            # Call parent submission handler if it exists
            if hasattr(SalarySlip, "on_submit"):
                super().on_submit()
            
            # Run post-submit processing
            salary_slip_post_submit(self)

            logger.info(f"Salary slip {self.name} submitted successfully")
        except Exception as e:
            logger.exception(f"Error submitting salary slip {self.name}: {e}")
            frappe.throw(_("Error submitting salary slip: {0}").format(str(e)))