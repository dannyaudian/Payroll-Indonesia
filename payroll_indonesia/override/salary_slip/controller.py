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
from payroll_indonesia.utils import get_status_pajak
from payroll_indonesia.utils import get_ptkp_to_ter_mapping, get_ter_rate

logger = logging.getLogger(__name__)


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Custom Salary Slip class for Indonesian payroll with proper tax calculations.
    Overrides the standard ERPNext tax calculations to use Indonesian PPh 21 calculations.
    """
    
    def validate(self):
        """Override validate to ensure our tax calculation is used."""
        # Call parent validate but we'll handle tax calculation ourselves
        super().validate()
        
        # Set a flag to indicate this is an Indonesian Payroll Salary Slip
        self.is_indonesia_payroll = True
    
    def get_income_tax_slabs(self):
        """
        Override income tax slab retrieval to use Indonesian tax slabs.
        This ensures ERPNext's standard tax calculation is bypassed.
        
        Returns:
            Dict: A dummy tax slab object with required attributes
        """
        # Instead of an empty list, return a dummy object with required attributes
        class DummyTaxSlab:
            def __init__(self):
                self.allow_tax_exemption = 0
                self.slabs = []
                self.other_taxes_and_charges = []
                
        return DummyTaxSlab()
    
    def get_tax_paid_in_period(self):
        """
        Override to prevent standard tax calculation.
        
        Returns:
            float: 0.0 as we're handling this differently
        """
        # Return 0 as we're handling tax in our own way
        return 0.0
    
    def compute_taxable_earnings_for_year(self):
        """
        Override to use our own implementation that doesn't depend on payroll period.
        """
        # Set a value for annual taxable earnings to prevent errors
        self.annual_taxable_earnings = self.gross_pay * 12
        self.gross_taxable_earnings_to_date = self.gross_pay
        
        # We'll use our own implementation in calculate_income_tax
        self.tax_slab = self.get_income_tax_slabs()

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

    def calculate_variable_tax(self, tax_component):
        """
        Override variable tax calculation to use our custom method.
        This is a critical override to prevent ERPNext from using its standard tax calculation.
        
        Args:
            tax_component: Tax component name
            
        Returns:
            float: Tax amount
        """
        # If this is PPh 21, use our custom calculation
        if tax_component == "PPh 21":
            result = self.calculate_income_tax(tax_component=tax_component)
            return result["tax_amount"]
        
        # For other tax components, fall back to standard calculation
        return super().calculate_variable_tax(tax_component)

    def calculate_variable_based_on_taxable_salary(self, tax_component):
        """
        Override to use our custom method for PPh 21.
        
        Args:
            tax_component: Tax component name
            
        Returns:
            float: Tax amount
        """
        # If this is PPh 21, use our custom calculation
        if tax_component == "PPh 21":
            return self.calculate_variable_tax(tax_component)
        
        # For other components, fall back to standard calculation
        return super().calculate_variable_based_on_taxable_salary(tax_component)

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

    def calculate_component_amounts(self, component_type):
        """
        Override to ensure our tax calculation is used.
        
        Args:
            component_type: Type of component (earnings or deductions)
        """
        # Call parent method to handle standard components
        super().calculate_component_amounts(component_type)
        
        # If this is deductions, handle our tax components specially
        if component_type == "deductions":
            self.update_indonesia_tax_components()

    def update_indonesia_tax_components(self):
        """Update tax components with our custom calculation."""
        if not hasattr(self, "deductions") or not self.deductions:
            return
            
        # Find PPh 21 component
        for deduction in self.deductions:
            if deduction.salary_component == "PPh 21":
                # Calculate tax based on settings
                settings = frappe.get_cached_doc("Payroll Indonesia Settings")
                tax_method = settings.tax_calculation_method
                
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
                        deduction.amount = result.get("monthly_tax", 0.0)
                        self.pph21 = deduction.amount
                    else:
                        result = tax_calc.calculate_monthly_pph_progressive(self)
                        deduction.amount = result.get("monthly_tax", 0.0)
                        self.pph21 = deduction.amount
                elif getattr(self, "is_december_override", 0):
                    result = tax_calc.calculate_december_pph(self)
                    deduction.amount = result.get("correction", 0.0)
                    self.pph21 = deduction.amount
                else:
                    result = tax_calc.calculate_monthly_pph_progressive(self)
                    deduction.amount = result.get("monthly_tax", 0.0)
                    self.pph21 = deduction.amount
                break
    
    def add_tax_components(self):
        """
        Override to use our own tax calculation.
        """
        # Only add the components if needed
        tax_components = ["PPh 21"]
        
        # Only process if we have deductions
        if not hasattr(self, "deductions") or not self.deductions:
            return
            
        # Check if PPh 21 component already exists
        pph21_exists = False
        for d in self.deductions:
            if d.salary_component == "PPh 21":
                pph21_exists = True
                break
                
        # If not, add it
        if not pph21_exists:
            # Get PPh 21 component details
            component = frappe.db.get_value(
                "Salary Component", 
                "PPh 21", 
                ["name", "salary_component_abbr", "do_not_include_in_total"],
                as_dict=1
            )
            
            if component:
                # Add to deductions
                self.append("deductions", {
                    "salary_component": component.name,
                    "abbr": component.salary_component_abbr,
                    "amount": 0,
                    "do_not_include_in_total": component.do_not_include_in_total,
                    "depends_on_payment_days": 0
                })
                
        # Now calculate tax for existing components
        self.update_indonesia_tax_components()