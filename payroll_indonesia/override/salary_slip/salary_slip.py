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
from payroll_indonesia.override.salary_slip_functions import salary_slip_post_submit
from payroll_indonesia.frappe_helpers import logger

__all__ = ["IndonesiaPayrollSalarySlip"]


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Enhanced Salary Slip for Indonesian Payroll.
    
    Extends the standard Salary Slip with support for Indonesian tax regulations,
    BPJS calculations, and year-end tax corrections.
    """

    def validate(self):
        """
        Validate salary slip with Indonesian payroll requirements.
        
        Performs standard validation and prepares for Indonesian-specific calculations.
        """
        try:
            # Call parent validation first
            super().validate()
            
            # Future: add Indonesia-specific validation logic
            # This will be implemented via helpers to keep this controller clean
            
            logger.info(f"Validation completed for {self.name}")
        except Exception as e:
            logger.exception(f"Error validating salary slip {self.name}: {e}")
            frappe.throw(_("Error validating salary slip: {0}").format(str(e)))

    def on_submit(self):
        """
        Process document on submission.
        
        Executes post-submission tasks such as:
        - Standard salary slip submission processing
        - Indonesian tax and BPJS record updates
        - Tax summary generation
        """
        try:
            # Call parent submission handler first
            super().on_submit()
            
            # Run post-submit processing via helper function
            salary_slip_post_submit(self)
            
            logger.info(f"Salary slip {self.name} submitted successfully")
        except Exception as e:
            logger.exception(f"Error submitting salary slip {self.name}: {e}")
            frappe.throw(_("Error submitting salary slip: {0}").format(str(e)))