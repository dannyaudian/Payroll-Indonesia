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
            
            # Handle date details
            if not self.salary_slip_based_on_timesheet:
                self.get_date_details()
            
            # Handle loan repayment and employee details
            self.validate_loan_repayment()
            self.validate_employee_details()
            
            # Handle attendance validation if not timesheet-based
            if not self.salary_slip_based_on_timesheet:
                self.validate_attendance()
            
            # Process components
            self.validate_components_with_flexible_benefits()
            
            # Load employee doc for tax calculations
            self._load_employee_doc()
            
            # Update components with Indonesian calculations
            update_component_amount(self)
            
            # Calculate net pay and set status
            self.calculate_net_pay()
            self.set_status()
            
            logger.info(f"Indonesia payroll validation completed for {self.name}")
        except Exception as e:
            logger.exception(f"Error validating salary slip {self.name}: {e}")
            frappe.throw(_("Error validating salary slip: {0}").format(str(e)))

    def validate_payroll_period(self):
        """
        Override to bypass the standard payroll period validation.
        
        This method is intentionally empty to bypass validation.
        """
        logger.debug(f"Bypassing payroll period validation for {self.name}")
        return True

    def _load_employee_doc(self):
        """Load employee document if not already loaded."""
        if not hasattr(self, "employee_doc") and self.employee:
            try:
                self.employee_doc = frappe.get_doc("Employee", self.employee)
            except Exception as e:
                logger.warning(f"Could not load employee_doc for {self.employee}: {e}")

    def calculate_totals(self) -> None:
        """Backward-compat wrapper used by salary_slip_functions."""
        self.calculate_net_pay()

    def on_submit(self):
        """
        Process document on submission.

        Executes submission and post-submission tasks for Indonesian payroll.
        """
        try:
            # Ensure fields are initialized
            initialize_fields(self)
            
            # Call parent submission handler
            super().on_submit()

            # Run post-submit processing
            salary_slip_post_submit(self)

            logger.info(f"Salary slip {self.name} submitted successfully")
        except Exception as e:
            logger.exception(f"Error submitting salary slip {self.name}: {e}")
            frappe.throw(_("Error submitting salary slip: {0}").format(str(e)))