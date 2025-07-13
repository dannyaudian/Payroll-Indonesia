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
    
    def before_insert(self):
        """
        Prepare Salary Slip before insertion.
        
        This method ensures the December override flag is set
        before the document is inserted into the database.
        """
        # Call parent's before_insert if it exists
        if hasattr(super(), "before_insert"):
            super().before_insert()
            
        # Set December override flag from Payroll Entry
        self._populate_december_override_from_payroll_entry()
        
        # Make sure run_as_december and is_december_override are in sync
        self._ensure_december_flags_consistency()
        
    def before_save(self):
        """
        Process before saving the document.
        
        Ensures flag consistency and handles other pre-save operations.
        """
        # Call parent's before_save if it exists
        if hasattr(super(), "before_save"):
            super().before_save()
            
        # Ensure December flags are consistent
        self._ensure_december_flags_consistency()
        
    def validate(self):
        """
        Validate Salary Slip with Indonesian-specific requirements.
        
        Extends the standard validation with additional checks and
        sets up fields required for Indonesian payroll processing.
        """
        # Process December override first - before any other validations
        # This ensures tax calculations use the correct mode
        # We call this even if already called in before_insert for safety
        # (in case document was created through other means)
        self._populate_december_override_from_payroll_entry()
        
        # Ensure December flags are consistent
        self._ensure_december_flags_consistency()
        
        # Process December override effects
        self._process_december_override()
        
        # Check TER method settings
        self._populate_ter_method_from_payroll_entry()
        
        # Validate required Indonesian fields
        self._validate_indonesian_fields()
        
        # Call the parent validation after our special overrides
        # This ensures our logic has priority over standard behavior
        super().validate()
    
    def _ensure_december_flags_consistency(self):
        """
        Ensure that run_as_december and is_december_override flags are consistent.
        
        This method synchronizes both flags so they always have the same value,
        regardless of which one was set originally.
        """
        # Initialize the flags if they don't exist
        if not hasattr(self, "run_as_december"):
            self.run_as_december = 0
            
        if not hasattr(self, "is_december_override"):
            self.is_december_override = 0
            
        # Synchronize the flags in both directions
        if self.run_as_december and not self.is_december_override:
            self.is_december_override = 1
            logger.debug(f"Set is_december_override=1 based on run_as_december for slip {getattr(self, 'name', 'new')}")
            
        elif self.is_december_override and not self.run_as_december:
            self.run_as_december = 1
            logger.debug(f"Set run_as_december=1 based on is_december_override for slip {getattr(self, 'name', 'new')}")
            
        # Log the final state for debugging
        logger.debug(f"December flags for slip {getattr(self, 'name', 'new')}: "
                     f"run_as_december={self.run_as_december}, "
                     f"is_december_override={self.is_december_override}")
    
    def _populate_december_override_from_payroll_entry(self):
        """
        Auto-populate is_december_override flag from Payroll Entry.
        
        This method checks the associated Payroll Entry document and sets
        the is_december_override flag on the Salary Slip accordingly.
        The field is read-only and can only be set by this method.
        
        It's safe to call this method multiple times as it will only 
        update the flag if needed and has proper error handling.
        """
        # Skip if the flag is already set to avoid unnecessary processing
        if getattr(self, "is_december_override", 0) == 1:
            logger.debug(f"December override already active for slip {getattr(self, 'name', 'new')}")
            return
            
        # Skip if no payroll entry - handle manually created slips
        if not getattr(self, "payroll_entry", None):
            logger.debug(f"No Payroll Entry for slip {getattr(self, 'name', 'new')}, skipping December override check")
            return
            
        # Initialize is_december_override to 0 if not already set
        if not hasattr(self, "is_december_override"):
            self.is_december_override = 0
            
        try:
            # Load the Payroll Entry document if it's a string
            payroll_entry_doc = None
            if isinstance(self.payroll_entry, str):
                payroll_entry_doc = frappe.get_doc("Payroll Entry", self.payroll_entry)
                # Store the document for future reference
                self.payroll_entry = payroll_entry_doc
            else:
                # It's already a document
                payroll_entry_doc = self.payroll_entry
                
            # Safety check in case payroll_entry is empty string or None
            if not payroll_entry_doc:
                logger.debug(f"Empty Payroll Entry for slip {getattr(self, 'name', 'new')}")
                return
                
            # Check for December override flags in Payroll Entry (try both field names)
            is_december = False
            
            # Try is_december_override first
            if hasattr(payroll_entry_doc, 'is_december_override') and payroll_entry_doc.is_december_override:
                is_december = True
                
            # Also check run_as_december
            elif hasattr(payroll_entry_doc, 'run_as_december') and payroll_entry_doc.run_as_december:
                is_december = True
                
            # Set flag on salary slip if needed
            if is_december:
                self.is_december_override = 1
                
                # Also set run_as_december for consistency
                if hasattr(self, "run_as_december"):
                    self.run_as_december = 1
                
                # Log the inheritance
                slip_name = getattr(self, 'name', 'new')
                pe_name = getattr(payroll_entry_doc, 'name', 'unknown')
                logger.info(f"December override flags inherited for slip {slip_name} from Payroll Entry {pe_name}")
                
        except Exception as e:
            # Log but don't interrupt flow
            logger.warning(
                f"Error checking December override from Payroll Entry for slip {getattr(self, 'name', 'new')}: {str(e)}"
            )
            
    def _populate_ter_method_from_payroll_entry(self):
        """
        Auto-populate use_ter_method flag from Payroll Entry.
        
        This method checks the associated Payroll Entry document and sets
        the use_ter_method flag on the Salary Slip accordingly.
        """
        # Skip if the flag is already set to avoid unnecessary processing
        if getattr(self, "use_ter_method", 0) == 1:
            logger.debug(f"TER method already active for slip {getattr(self, 'name', 'new')}")
            return
            
        # Skip if no payroll entry - handle manually created slips
        if not getattr(self, "payroll_entry", None):
            logger.debug(f"No Payroll Entry for slip {getattr(self, 'name', 'new')}, skipping TER method check")
            return
            
        # Initialize use_ter_method to 0 if not already set
        if not hasattr(self, "use_ter_method"):
            self.use_ter_method = 0
            
        try:
            # Get the Payroll Entry document
            payroll_entry_doc = None
            if isinstance(self.payroll_entry, str):
                payroll_entry_doc = frappe.get_doc("Payroll Entry", self.payroll_entry)
                # Store the document for future reference
                self.payroll_entry = payroll_entry_doc
            else:
                # It's already a document
                payroll_entry_doc = self.payroll_entry
                
            # Safety check in case payroll_entry is empty string or None
            if not payroll_entry_doc:
                return
                
            # Check for use_ter_method attribute safely
            if hasattr(payroll_entry_doc, 'use_ter_method') and payroll_entry_doc.use_ter_method:
                # Set flag on salary slip
                self.use_ter_method = 1
                
                # Log the inheritance
                slip_name = getattr(self, 'name', 'new')
                pe_name = getattr(payroll_entry_doc, 'name', 'unknown')
                logger.info(f"TER method flag inherited for slip {slip_name} from Payroll Entry {pe_name}")
                
        except Exception as e:
            # Log but don't interrupt flow
            logger.warning(
                f"Error checking TER method from Payroll Entry for slip {getattr(self, 'name', 'new')}: {str(e)}"
            )
    
    def _process_december_override(self):
        """
        Process December override logic for annual tax correction.
        
        Only uses is_december flag (determined by salary_slip_functions.is_december)
        to determine if annual tax correction should be applied.
        This allows the flag to be determined flexibly based on either the document field
        or inheritance from Payroll Entry.
        """
        # Use is_december() function which checks both direct flag and inherited flags
        if is_december(self):
            # Add or update payroll note with December correction information
            december_note = _("Annual tax correction (December) is applied to this salary slip")
            
            if getattr(self, "payroll_note", ""):
                if december_note not in self.payroll_note:
                    self.payroll_note = f"{self.payroll_note}\n{december_note}"
            else:
                self.payroll_note = december_note
                
            logger.info(f"December tax correction mode is active for salary slip {getattr(self, 'name', 'new')}")
    
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
                
        # Ensure December flags are set
        if not hasattr(self, "is_december_override"):
            self.is_december_override = 0
            
        if not hasattr(self, "run_as_december"):
            self.run_as_december = 0
            
        # Ensure TER method flag is set
        if not hasattr(self, "use_ter_method"):
            self.use_ter_method = 0
    
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