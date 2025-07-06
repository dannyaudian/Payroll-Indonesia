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
    initialize_fields
)
from payroll_indonesia.frappe_helpers import logger

__all__ = ["IndonesiaPayrollSalarySlip"]


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Enhanced Salary Slip for Indonesian Payroll.

    Extends the standard Salary Slip with support for Indonesian tax regulations,
    BPJS calculations, and year-end tax corrections.
    
    Overrides validate_payroll_period to bypass the standard Frappe validation.
    """

    def validate(self):
        """
        Validate salary slip with Indonesian payroll requirements.

        Performs standard validation and prepares for Indonesian-specific calculations.
        Overrides the parent validate to bypass certain checks if needed.
        """
        try:
            # Initialize fields first
            initialize_fields(self)
            
            # Call parent validation with custom modifications
            self._modified_parent_validate()
            
            # Run additional Indonesian-specific validations
            self._validate_indonesian_fields()

            logger.info(f"Indonesia payroll validation completed for {self.name}")
        except Exception as e:
            logger.exception(f"Error validating salary slip {self.name}: {e}")
            frappe.throw(_("Error validating salary slip: {0}").format(str(e)))

    def _modified_parent_validate(self):
        """
        Modified version of parent validate to bypass payroll period validation.
        
        This method calls all the parent validation methods except validate_payroll_period.
        """
        # Call all methods from parent validate except validate_payroll_period
        
        # These methods are from SalarySlip.validate() in hrms.payroll.doctype.salary_slip.salary_slip
        if not self.salary_slip_based_on_timesheet:
            self.get_date_details()
        
        # Bypass payroll period validation
        # self.validate_payroll_period()  # This line is intentionally commented out
        
        # Continue with other validations from parent
        self.validate_loan_repayment()
        self.validate_employee_details()
        if not self.salary_slip_based_on_timesheet:
            self.validate_attendance()
        self.validate_components_with_flexible_benefits()
        
        # Use calculate_net_pay instead of compute_component_amounts to ensure
        # our custom components are calculated properly
        self.calculate_net_pay()
        self.set_status()

    def validate_payroll_period(self):
        """
        Override of validate_payroll_period to bypass the standard validation.
        
        This method is intentionally empty to bypass the standard payroll period validation.
        """
        # Bypass the standard payroll period validation
        logger.debug(f"Bypassing payroll period validation for {self.name}")
        return True

    def _validate_indonesian_fields(self):
        """
        Validate Indonesia-specific fields.
        
        Performs additional validations specific to Indonesian payroll.
        """
        # Ensure employee_doc is loaded
        if not hasattr(self, "employee_doc") and self.employee:
            try:
                self.employee_doc = frappe.get_doc("Employee", self.employee)
            except Exception as e:
                logger.warning(f"Could not load employee_doc for {self.employee}: {e}")
        
        # Additional validations can be added here

    def calculate_totals(self) -> None:
        """Backward-compat wrapper used by salary_slip_functions."""
        # Recompute earnings, deductions, and net pay
        self.calculate_net_pay()

    def on_submit(self):
        """
        Process document on submission.

        Executes standard submission and then post-submission tasks for Indonesian payroll.
        """
        try:
            # Ensure fields are initialized
            initialize_fields(self)
            
            # Call parent submission handler first
            super().on_submit()

            # Run post-submit processing via helper function
            salary_slip_post_submit(self)

            logger.info(f"Salary slip {self.name} submitted successfully")
        except Exception as e:
            logger.exception(f"Error submitting salary slip {self.name}: {e}")
            frappe.throw(_("Error submitting salary slip: {0}").format(str(e)))