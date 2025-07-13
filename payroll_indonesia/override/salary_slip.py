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
from payroll_indonesia.override.salary_slip_functions import is_december

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
        # Process December override first - before any other validations
        # This ensures tax calculations use the correct mode
        self._populate_december_override_from_payroll_entry()
        self._process_december_override()
        
        # Validate required Indonesian fields
        self._validate_indonesian_fields()
        
        # Call the parent validation after our special overrides
        # This ensures our logic has priority over standard behavior
        super().validate()
    
    def _populate_december_override_from_payroll_entry(self):
        """
        Auto-populate is_december_override flag from Payroll Entry.
        
        This method checks the associated Payroll Entry document and sets
        the is_december_override flag on the Salary Slip accordingly.
        The field is read-only and can only be set by this method.
        """
        # Initialize is_december_override to 0
        self.is_december_override = 0
        
        if self.payroll_entry:
            # Load the Payroll Entry document if it's a string
            try:
                payroll_entry_doc = (
                    frappe.get_doc("Payroll Entry", self.payroll_entry)
                    if isinstance(self.payroll_entry, str)
                    else self.payroll_entry
                )

                # Ensure self.payroll_entry holds the loaded document for
                # functions that expect the Payroll Entry doc
                self.payroll_entry = payroll_entry_doc
                
                # Set is_december_override based on the Payroll Entry setting
                # directly from the document field without any month validation
                if hasattr(payroll_entry_doc, 'is_december_override') and payroll_entry_doc.is_december_override:
                    self.is_december_override = 1
                    logger.info(f"December override activated for slip {self.name} from Payroll Entry {payroll_entry_doc.name}")
            except Exception as e:
                logger.warning(f"Could not check payroll_entry.is_december_override for {self.name}: {e}")
    
    def _process_december_override(self):
        """
        Process December override logic for annual tax correction.
        
        Only uses is_december_override field to determine if annual tax correction
        should be applied.
        """
        if is_december(self):
            # Add or update payroll note with December correction information
            december_note = _("Annual tax correction (December) is applied to this salary slip")
            
            if self.payroll_note:
                if december_note not in self.payroll_note:
                    self.payroll_note = f"{self.payroll_note}\n{december_note}"
            else:
                self.payroll_note = december_note
                
            logger.info(f"December tax correction mode is active for salary slip {self.name}")
    
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