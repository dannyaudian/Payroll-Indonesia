# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:35:42 by dannyaudian

"""
Salary Slip override for Indonesian payroll.

This module provides a custom implementation of the Salary Slip document
for Indonesian payroll processing, with support for:
- BPJS (social security) calculations
- PPh 21 tax calculations (progressive and TER methods)
- December year-end tax correction
- YTD tracking and reporting
"""

from typing import Any, Dict

import frappe
from frappe import _
from frappe.utils import flt
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

# Import calculators
import payroll_indonesia.override.salary_slip.bpjs_calculator as bpjs_calc
import payroll_indonesia.override.salary_slip.tax_calculator as tax_calc
import payroll_indonesia.override.salary_slip.ter_calculator as ter_calc

# Import validation module and helpers
import payroll_indonesia.payroll_indonesia.validations as validations
from payroll_indonesia.override.salary_slip_functions import (
    initialize_fields, 
    salary_slip_post_submit,
    _is_december_calculation,
    _should_use_ter
)

# Import utilities
from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.override.salary_slip.salary_utils import calculate_ytd_and_ytm
from payroll_indonesia.frappe_helpers import logger

__all__ = ["IndonesiaPayrollSalarySlip"]


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Enhanced Salary Slip for Indonesian Payroll.
    
    Extends the standard Salary Slip with support for Indonesian tax regulations,
    BPJS calculations, and year-end tax corrections.
    """

    def validate(self) -> None:
        """
        Validate salary slip with Indonesian payroll requirements.
        
        Performs employee data validation, field initialization,
        and calculates all Indonesian payroll components.
        """
        try:
            # Call parent validation first
            super().validate()

            # Validate employee data
            self._validate_employee_data()

            # Initialize additional fields
            initialize_fields(self)

            # Calculate components
            self.calculate()

            logger.info(f"Validation completed for {self.name}")
        except Exception as e:
            logger.exception(f"Error validating salary slip {self.name}: {e}")
            frappe.throw(_("Error validating salary slip: {0}").format(str(e)))

    def _validate_employee_data(self) -> None:
        """
        Validate employee data required for Indonesian payroll.
        
        Checks for valid tax status and other employee-specific requirements.
        Stores the employee document for later use in calculations.
        """
        if not self.employee:
            frappe.throw(_("Employee is required"), title=_("Missing Data"))

        # Get employee document
        employee_doc = frappe.get_doc("Employee", self.employee)

        # Validate tax status if available
        if hasattr(employee_doc, "status_pajak"):
            validations.validate_tax_status(employee_doc.status_pajak)

        # Validate other employee fields
        validations.validate_employee_fields(employee_doc)

        # Store reference to employee document
        self.employee_doc = employee_doc

    def calculate(self) -> None:
        """
        Calculate all components for Indonesian payroll.
        
        Orchestrates the calculation of BPJS, YTD values, taxes,
        and ensures totals are properly updated.
        """
        # Get configuration
        cfg = get_live_config()

        # Calculate BPJS components
        self._calculate_bpjs()

        # Calculate YTD values
        self._calculate_ytd_values()

        # Calculate tax based on method from config
        self._calculate_tax(cfg)

        # Update totals
        self._update_totals()

    def _calculate_bpjs(self) -> None:
        """
        Calculate BPJS components using the BPJS calculator.
        
        Updates both the salary slip fields and deduction components
        with the calculated BPJS values.
        """
        try:
            # Calculate BPJS components
            bpjs_components = bpjs_calc.calculate_components(self)

            # Store total BPJS employee contribution
            if hasattr(self, "total_bpjs"):
                self.total_bpjs = bpjs_components.get("total_employee", 0)

            # Store individual components
            for component in ["kesehatan_employee", "jht_employee", "jp_employee"]:
                if hasattr(self, component):
                    setattr(self, component, bpjs_components.get(component, 0))

            # Update BPJS components in deductions
            self._update_bpjs_deductions(bpjs_components)

            logger.debug(f"BPJS calculated for {self.name}: {bpjs_components}")
        except Exception as e:
            logger.exception(f"Error calculating BPJS: {e}")
            frappe.throw(_("Error calculating BPJS: {0}").format(str(e)))

    def _update_bpjs_deductions(self, components: Dict[str, float]) -> None:
        """
        Update BPJS component amounts in deductions.
        
        Args:
            components: Dictionary of calculated BPJS components
        """
        if not hasattr(self, "deductions") or not self.deductions:
            return

        # Mapping of component names to values
        component_map = {
            "BPJS Kesehatan Employee": "kesehatan_employee",
            "BPJS JHT Employee": "jht_employee",
            "BPJS JP Employee": "jp_employee",
        }

        # Update each component in deductions
        for deduction in self.deductions:
            component_name = getattr(deduction, "salary_component", "")
            if component_name in component_map:
                key = component_map[component_name]
                deduction.amount = components.get(key, 0)

    def _calculate_ytd_values(self) -> None:
        """
        Calculate YTD values for gross pay and BPJS deductions.
        
        Uses the salary_utils.calculate_ytd_and_ytm function to retrieve
        year-to-date values and updates the salary slip fields accordingly.
        """
        try:
            ytd_values = calculate_ytd_and_ytm(self)

            if hasattr(self, "ytd_gross_pay"):
                self.ytd_gross_pay = ytd_values.get("ytd", {}).get("ytd_gross", 0)

            if hasattr(self, "ytd_bpjs_deductions"):
                self.ytd_bpjs_deductions = ytd_values.get("ytd", {}).get("ytd_bpjs", 0)

            if hasattr(self, "ytd_pph21"):
                self.ytd_pph21 = ytd_values.get("ytd", {}).get("ytd_pph21", 0)

            logger.debug(f"YTD values calculated for {self.name}")
        except Exception as e:
            logger.warning(f"Error calculating YTD values: {e}")
            # Non-critical error, continue processing

    def _calculate_tax(self, cfg: Dict[str, Any]) -> None:
        """
        Calculate tax based on method from config.
        
        Determines which tax calculation method to use (December, TER, or Progressive)
        and applies the appropriate calculation.
        
        Args:
            cfg: Configuration dictionary
        """
        try:
            # Determine calculation method
            is_december = _is_december_calculation(self)
            is_using_ter = _should_use_ter(self, cfg)

            # Use appropriate calculation method
            if is_december:
                logger.info(f"Using December tax calculation for {self.name}")
                tax_calc.calculate_december_pph(self)
            elif is_using_ter:
                logger.info(f"Using TER tax calculation for {self.name}")
                ter_calc.calculate_monthly_pph_with_ter(self)
            else:
                logger.info(f"Using progressive tax calculation for {self.name}")
                tax_calc.calculate_monthly_pph_progressive(self)

            # Update PPh 21 component in deductions
            self._update_pph21_deduction()
        except Exception as e:
            logger.exception(f"Error calculating tax: {e}")
            frappe.throw(_("Error calculating tax: {0}").format(str(e)))

    def _update_pph21_deduction(self) -> None:
        """
        Update PPh 21 component in deductions with calculated amount.
        
        Either updates an existing PPh 21 component or adds a new one
        if it doesn't exist and the amount is greater than zero.
        """
        if not hasattr(self, "deductions") or not self.deductions:
            return

        pph21_amount = flt(getattr(self, "pph21", 0))

        # Look for PPh 21 component in deductions
        for deduction in self.deductions:
            if getattr(deduction, "salary_component", "") == "PPh 21":
                deduction.amount = pph21_amount
                return

        # If not found and amount > 0, add it
        if pph21_amount > 0:
            # Add PPh 21 component if it doesn't exist
            self.append(
                "deductions",
                {
                    "salary_component": "PPh 21",
                    "amount": pph21_amount,
                    "default_amount": pph21_amount,
                    "abbr": "PPh21",
                },
            )

    def _update_totals(self) -> None:
        """
        Update total deduction to include BPJS and PPh 21.
        
        Recalculates the total deduction amount based on all deduction components
        and updates the net pay accordingly.
        """
        if not hasattr(self, "total_deduction"):
            return

        # Calculate sum of all deductions to ensure consistency
        total = 0
        if hasattr(self, "deductions") and self.deductions:
            for deduction in self.deductions:
                total += flt(getattr(deduction, "amount", 0))

        self.total_deduction = total

        # Update net pay if gross pay exists
        if hasattr(self, "gross_pay") and hasattr(self, "net_pay"):
            self.net_pay = flt(self.gross_pay) - flt(self.total_deduction)

    def on_submit(self) -> None:
        """
        Process document on submission.
        
        Executes post-submission tasks such as:
        - Updating related tax and BPJS records
        - Enqueueing tax summary updates
        - Updating employee YTD records
        """
        try:
            # Call parent submission handler
            super().on_submit()
            
            # Run post-submit processing (tax summaries, etc.)
            salary_slip_post_submit(self)
            
            logger.info(f"Salary slip {self.name} submitted successfully")
        except Exception as e:
            logger.exception(f"Error submitting salary slip {self.name}: {e}")
            frappe.throw(_("Error submitting salary slip: {0}").format(str(e)))
