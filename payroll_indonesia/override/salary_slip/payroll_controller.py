# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:13:48 by dannyaudian

"""
Salary Slip controller override for Payroll Indonesia.
"""

import logging
from typing import Any, Dict, Optional

import frappe
from frappe import _

import payroll_indonesia.override.salary_slip.bpjs_calculator as bpjs_calc
import payroll_indonesia.override.salary_slip.tax_calculator as tax_calc
import payroll_indonesia.override.salary_slip.ter_calculator as ter_calc
import payroll_indonesia.payroll_indonesia.validations as validations

logger = logging.getLogger('payroll_controller')


class PayrollController:
    """
    Controller for Salary Slip document.
    Overrides standard behavior with Indonesia-specific logic.
    """

    def __init__(self, doc: Any) -> None:
        """
        Initialize PayrollController with document.
        
        Args:
            doc: Salary Slip document
        """
        self.doc = doc
        self.name = getattr(doc, 'name', 'New')
        self.doc_type = getattr(doc, 'doctype', 'Salary Slip')
        
        logger.info(f"PayrollController initialized for {self.doc_type}: {self.name}")
        
        # Initialize additional fields if needed
        self._initialize_fields()

    def validate(self) -> None:
        """
        Validate document based on its type.
        Delegates to appropriate validation module.
        """
        logger.info(f"Validating {self.doc_type}: {self.name}")
        
        try:
            if self.doc_type == 'BPJS Settings':
                validations.validate_bpjs_settings(self.doc)
            elif self.doc_type == 'PPh 21 Settings':
                validations.validate_pph21_settings(self.doc)
            elif self.doc_type == 'Employee':
                validations.validate_employee_golongan(self.doc)
            elif self.doc_type == 'Salary Slip':
                self._validate_salary_slip()
                
            logger.info(f"Validation completed for {self.doc_type}: {self.name}")
        except Exception as e:
            logger.error(f"Validation error for {self.doc_type}: {str(e)}")
            raise

    def on_validate(self) -> None:
        """
        Override validation method for Salary Slip.
        Called by Salary Slip hooks during validation.
        """
        logger.info(f"On validate for Salary Slip: {self.name}")
        
        try:
            # Calculate BPJS components
            bpjs_components = bpjs_calc.calculate_components(self.doc)
            
            # Store calculated values
            self._store_bpjs_values(bpjs_components)
            
            # Calculate tax based on method
            self._calculate_tax()
            
            # Update total deductions
            self._update_totals()
            
            logger.info(f"On validate completed for Salary Slip: {self.name}")
        except Exception as e:
            logger.error(f"On validate error for Salary Slip: {str(e)}")
            raise

    def on_submit(self) -> None:
        """
        Process document on submission.
        Delegates to appropriate processing module.
        """
        logger.info(f"Processing submission for {self.doc_type}: {self.name}")
        
        try:
            if self.doc_type == 'Salary Slip':
                self._process_salary_slip_submission()
            
            logger.info(f"Submission processing completed for {self.name}")
        except Exception as e:
            logger.error(f"Submission processing error: {str(e)}")
            raise

    def _initialize_fields(self) -> None:
        """
        Initialize additional fields required for Indonesia payroll.
        """
        if self.doc_type != 'Salary Slip':
            return
            
        defaults = {
            "biaya_jabatan": 0,
            "netto": 0,
            "total_bpjs": 0,
            "is_using_ter": 0,
            "ter_rate": 0,
            "koreksi_pph21": 0,
        }
        
        for field, default in defaults.items():
            if not hasattr(self.doc, field) or getattr(self.doc, field) is None:
                setattr(self.doc, field, default)

    def _validate_salary_slip(self) -> None:
        """
        Validate Salary Slip document.
        Delegates to BPJS and tax calculators.
        """
        # Calculate BPJS components
        bpjs_components = bpjs_calc.calculate_components(self.doc)
        
        # Store total BPJS employee contribution
        if hasattr(self.doc, 'total_bpjs'):
            self.doc.total_bpjs = bpjs_components.get('total_employee', 0)
        
        # Determine tax calculation method
        if hasattr(self.doc, 'is_december_override') and self.doc.is_december_override:
            tax_calc.calculate_december_pph(self.doc)
        elif hasattr(self.doc, 'is_using_ter') and self.doc.is_using_ter:
            ter_calc.calculate_monthly_pph_with_ter(self.doc)
        else:
            tax_calc.calculate_monthly_pph_progressive(self.doc)

    def _store_bpjs_values(self, components: Dict[str, float]) -> None:
        """
        Store BPJS component values in the document.
        
        Args:
            components: Dictionary of BPJS components
        """
        if hasattr(self.doc, 'total_bpjs'):
            self.doc.total_bpjs = components.get('total_employee', 0)
            
        # Store individual components if fields exist
        for field in ['kesehatan_employee', 'jht_employee', 'jp_employee']:
            if hasattr(self.doc, field):
                setattr(self.doc, field, components.get(field, 0))

    def _calculate_tax(self) -> None:
        """
        Calculate tax based on appropriate method.
        """
        # Check December override first
        if hasattr(self.doc, 'is_december_override') and self.doc.is_december_override:
            tax_calc.calculate_december_pph(self.doc)
        elif hasattr(self.doc, 'is_using_ter') and self.doc.is_using_ter:
            ter_calc.calculate_monthly_pph_with_ter(self.doc)
        else:
            tax_calc.calculate_monthly_pph_progressive(self.doc)

    def _update_totals(self) -> None:
        """
        Update total earnings and deductions.
        """
        # This would be implemented in a real system
        # For demonstration purposes, just log the action
        logger.info(f"Updated totals for Salary Slip: {self.name}")

    def _process_salary_slip_submission(self) -> None:
        """
        Process Salary Slip submission.
        Updates related documents.
        """
        # Update YTD totals for the employee
        if hasattr(self.doc, 'employee') and self.doc.employee:
            self._update_ytd_totals()
        
        # Update tax summary
        self._update_tax_summary()
        
        # Queue any background tasks if needed
        self._queue_background_tasks()

    def _update_ytd_totals(self) -> None:
        """
        Update YTD totals for employee.
        """
        # This would be implemented in a real system
        # For demonstration purposes, just log the action
        logger.info(f"Updated YTD totals for employee {self.doc.employee}")

    def _update_tax_summary(self) -> None:
        """
        Update employee tax summary document.
        """
        # This would be implemented in a real system
        # For demonstration purposes, just log the action
        logger.info(f"Updated tax summary for employee {self.doc.employee}")

    def _queue_background_tasks(self) -> None:
        """
        Queue any background tasks needed after submission.
        """
        # This would be implemented in a real system
        # For demonstration purposes, just log the action
        logger.info(f"Queued background tasks for Salary Slip: {self.name}")
