# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Indonesia Payroll Salary Slip Controller

This module overrides ERPNext's Salary Slip class to implement Indonesian tax calculations.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

# Correct import paths based on ERPNext/HRMS structure
try:
    # For newer versions with HRMS app
    from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
except ImportError:
    try:
        # For older ERPNext versions
        from erpnext.hr.doctype.salary_slip.salary_slip import SalarySlip
    except ImportError:
        # Fallback
        from frappe.model.document import Document
        class SalarySlip(Document):
            pass

import logging
from typing import Dict, List, Any, Optional

import payroll_indonesia.override.salary_slip.tax_calculator as tax_calc
from payroll_indonesia.payroll_indonesia.utils import get_status_pajak
from payroll_indonesia.payroll_indonesia.utils import get_ptkp_to_ter_mapping, get_ter_rate

logger = logging.getLogger(__name__)


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Custom Salary Slip class for Indonesian payroll with proper tax calculations.
    Overrides the standard ERPNext tax calculations to use Indonesian PPh 21 calculations.
    """

    def get_income_tax_slabs(self):
        """
        Override income tax slab retrieval to use Indonesian tax slabs.
        This ensures ERPNext's standard tax calculation is bypassed.
        
        Returns:
            List: Empty list to bypass ERPNext's tax calculation
        """
        # Return empty list to bypass standard ERPNext tax calculation
        # Our custom tax calculation happens in get_income_tax
        return []

    def calculate_income_tax(self, payroll_period=None, tax_component=None):
        """
        Override income tax calculation to use Indonesian PPh 21 calculation.
        
        Args:
            payroll_period: Payroll period (unused)
            tax_component: Tax component (unused)
            
        Returns:
            Dict: Tax calculation result
        """
        # Calculate tax based on method from settings
        settings = frappe.get_cached_doc("Payroll Indonesia Settings")
        tax_method = settings.tax_calculation_method  # "TER" or "PROGRESSIVE"
        
        logger.info(f"Calculating income tax for {self.employee} using method: {tax_method}")
        
        if tax_method == "TER" and settings.use_ter:
            # Check if employee is eligible for TER
            status_pajak = get_status_pajak(self)
            mapping = get_ptkp_to_ter_mapping()
            ter_category = mapping.get(status_pajak, "")
            
            if ter_category:
                # Use TER calculation
                result = tax_calc.calculate_monthly_pph_with_ter(
                    ter_category=ter_category,
                    gross_pay=self.gross_pay,
                    slip=self
                )
                tax_amount = result.get("monthly_tax", 0.0)
                logger.info(f"TER method applied for {self.name} - tax: {tax_amount}")
            else:
                # Fallback to progressive if not TER eligible
                logger.info(f"Employee {self.employee} not eligible for TER, using progressive")
                result = tax_calc.calculate_monthly_pph_progressive(self)
                tax_amount = result.get("monthly_tax", 0.0)
        elif getattr(self, "is_december_override", 0):
            # Use December calculation for year-end
            result = tax_calc.calculate_december_pph(self)
            tax_amount = result.get("correction", 0.0)
            logger.info(f"December correction applied for {self.name} - tax: {tax_amount}")
        else:
            # Use standard progressive calculation
            result = tax_calc.calculate_monthly_pph_progressive(self)
            tax_amount = result.get("monthly_tax", 0.0)
            logger.info(f"Progressive method applied for {self.name} - tax: {tax_amount}")
        
        # Return the tax amount in the format expected by ERPNext
        return {
            "tax_amount": flt(tax_amount, 2),
            "tax_on_additional_salary": 0,
            "tax_on_flexible_benefit": 0,
            "tax_break_up": result
        }

    def calculate_taxable_earnings(self, include_flexi=0):
        """
        Override taxable earnings calculation.
        This ensures we use our own definition of taxable income.
        
        Args:
            include_flexi: Include flexible benefits (unused)
            
        Returns:
            float: Taxable earnings
        """
        # In Indonesia, taxable earnings are typically the gross pay
        # minus deductions allowed by tax regulations
        biaya_jabatan = min(self.gross_pay * (5 / 100), 500000)  # 5% up to 500k
        self.biaya_jabatan = biaya_jabatan
        
        # Use total_bpjs field if it exists, otherwise calculate from components
        bpjs_total = getattr(self, "total_bpjs", 0)
        if not bpjs_total:
            bpjs_total = self.get_bpjs_deductions()
        
        # Calculate netto
        netto = self.gross_pay - biaya_jabatan - bpjs_total
        self.netto = netto
        
        return netto

    def get_bpjs_deductions(self):
        """
        Calculate total BPJS deductions from components.
        
        Returns:
            float: Total BPJS deductions
        """
        bpjs_components = [
            "BPJS Kesehatan Employee",
            "BPJS JHT Employee",
            "BPJS JP Employee"
        ]
        
        total = 0
        if hasattr(self, "deductions"):
            for deduction in self.deductions:
                if deduction.salary_component in bpjs_components:
                    total += flt(deduction.amount)
        
        return total

    def set_component_amounts(self):
        """
        Override component amount calculation to ensure our tax calculation is used.
        """
        # First call the parent method to handle standard calculations
        super().set_component_amounts()
        
        # Then call our custom update function to handle Indonesian-specific components
        self.update_indonesia_components()

    def update_indonesia_components(self):
        """
        Update components specific to Indonesian payroll.
        """
        if not hasattr(self, "deductions") or not self.deductions:
            return
            
        # Calculate PPh 21 using our custom calculation
        settings = frappe.get_cached_doc("Payroll Indonesia Settings")
        tax_method = settings.tax_calculation_method
        
        # Find PPh 21 component
        pph21_component = None
        for deduction in self.deductions:
            if deduction.salary_component == "PPh 21":
                pph21_component = deduction
                break
                
        if not pph21_component:
            return
            
        # Calculate tax based on method
        if tax_method == "TER" and settings.use_ter:
            status_pajak = get_status_pajak(self)
            mapping = get_ptkp_to_ter_mapping()
            ter_category = mapping.get(status_pajak, "")
            
            if ter_category:
                result = tax_calc.calculate_monthly_pph_with_ter(
                    ter_category=ter_category,
                    gross_pay=self.gross_pay,
                    slip=self
                )
                pph21_component.amount = result.get("monthly_tax", 0.0)
                self.pph21 = pph21_component.amount
            else:
                result = tax_calc.calculate_monthly_pph_progressive(self)
                pph21_component.amount = result.get("monthly_tax", 0.0)
                self.pph21 = pph21_component.amount
        elif getattr(self, "is_december_override", 0):
            result = tax_calc.calculate_december_pph(self)
            pph21_component.amount = result.get("correction", 0.0)
            self.pph21 = pph21_component.amount
        else:
            result = tax_calc.calculate_monthly_pph_progressive(self)
            pph21_component.amount = result.get("monthly_tax", 0.0)
            self.pph21 = pph21_component.amount