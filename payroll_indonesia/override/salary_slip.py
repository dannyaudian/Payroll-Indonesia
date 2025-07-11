# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:35:42 by dannyaudian

"""
Salary Slip override for Indonesian payroll.

Re-exports IndonesiaPayrollSalarySlip from the override.salary_slip package.
This class contains customizations for Indonesian payroll regulations.
"""

import frappe
from frappe import _
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from frappe.utils import flt, getdate, cint

from payroll_indonesia.frappe_helpers import get_logger

logger = get_logger("salary_slip")


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Custom Salary Slip class for Indonesian payroll requirements.
    
    Extends the standard SalarySlip class with additional functionality
    for Indonesian tax calculations, BPJS, and other local requirements.
    """
    
    def validate(self):
        """
        Validate Salary Slip with Indonesian-specific requirements.
        
        Extends the standard validation with additional checks and
        sets up fields required for Indonesian payroll processing.
        """
        # Call the parent validation first
        super().validate()
        
        # Check for payroll_entry's is_december_override flag
        self._check_payroll_entry_december_override()
        
        # Process December logic if enabled
        self._process_december_override()
        
        # Additional validations can be added here
        self._validate_indonesian_fields()
    
    def _check_payroll_entry_december_override(self):
        """
        Check if payroll entry has is_december_override flag set.
        
        This method checks the associated Payroll Entry document and sets
        the is_december_override flag on the Salary Slip if needed.
        """
        if hasattr(self, "payroll_entry") and self.payroll_entry:
            # Load the Payroll Entry document if it's a string
            payroll_entry_doc = None
            try:
                if isinstance(self.payroll_entry, str):
                    payroll_entry_doc = frappe.get_doc("Payroll Entry", self.payroll_entry)
                else:
                    payroll_entry_doc = self.payroll_entry
                    
                # Set is_december_override based on the Payroll Entry setting
                if getattr(payroll_entry_doc, "is_december_override", 0):
                    self.is_december_override = 1
                    logger.info(f"Setting is_december_override=1 for {self.name} based on Payroll Entry")
            except Exception as e:
                logger.warning(f"Could not check payroll_entry.is_december_override for {self.name}: {e}")
    
    def _process_december_override(self):
        """
        Process December override logic for annual tax correction.
        
        If is_december_override is set, this activates the annual tax correction
        logic by setting bypass_annual_detection and updating the payroll note.
        """
        end_date = getattr(self, "end_date", None)
        is_december_month = False
        if end_date:
            try:
                is_december_month = getdate(end_date).month == 12
            except Exception:
                logger.warning(f"Invalid end_date for slip {getattr(self, 'name', '')}: {end_date}")

        if is_december_month or cint(getattr(self, "is_december_override", 0)) == 1:
            # Activate bypass to ensure annual correction is applied
            self.bypass_annual_detection = 1
            
            # Add or update payroll note with December correction information
            december_note = _("Annual tax correction (December) is applied to this salary slip")
            
            if hasattr(self, "payroll_note") and self.payroll_note:
                if december_note not in self.payroll_note:
                    self.payroll_note = f"{self.payroll_note}\n{december_note}"
            else:
                self.payroll_note = december_note
                
            logger.info(f"December correction activated for salary slip {self.name}")
    
    def _validate_indonesian_fields(self):
        """
        Validate fields required for Indonesian payroll processing.
        
        Ensures all required custom fields for Indonesian payroll
        are properly populated with appropriate values.
        """
        # Initialize custom fields if they don't exist
        required_fields = {
            "biaya_jabatan": 0,
            "netto": 0, 
            "total_bpjs": 0,
            "is_using_ter": 0,
            "ter_rate": 0,
            "koreksi_pph21": 0,
            "ytd_gross_pay": 0,
            "ytd_bpjs_deductions": 0,
            "is_december_override": 0,  # Ensure this field is initialized
        }
        
        for field, default_value in required_fields.items():
            if not hasattr(self, field) or getattr(self, field) is None:
                setattr(self, field, default_value)
    
    def calculate_tax_by_tax_slab(self):
        """
        Override calculate_tax_by_tax_slab to handle Indonesian tax calculation.
        
        This is a stub that returns zero because Indonesian tax calculation
        is handled by the salary_slip_functions hooks instead.
        
        Returns:
            float: Always returns 0 as tax is calculated separately
        """
        # Return 0 because Indonesian tax calculation is handled by hooks
        return 0
    
    def get_tax_paid_in_period(self):
        """
        Get tax paid in the current period for Indonesian tax calculation.
        
        Returns:
            float: Amount of tax paid in current period
        """
        # This function can be extended for Indonesian tax requirements
        # For now, use the parent implementation
        return super().get_tax_paid_in_period()


# Re-export the class for import by other modules
__all__ = ["IndonesiaPayrollSalarySlip"]
