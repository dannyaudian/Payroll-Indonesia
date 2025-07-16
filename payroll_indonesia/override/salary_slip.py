# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
Salary Slip - Main override for Indonesia-specific salary processing
"""

import logging
from typing import Dict, List, Tuple, Any, Optional, Union
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, date_diff, add_months

from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.config.config import get_component_tax_effect, get_live_config
from payroll_indonesia.constants import (
    TAX_DEDUCTION_EFFECT,
    TAX_OBJEK_EFFECT,
    TAX_NON_OBJEK_EFFECT,
    NATURA_OBJEK_EFFECT,
    NATURA_NON_OBJEK_EFFECT,
    MONTHS_PER_YEAR,
    BIAYA_JABATAN_MAX,
)
from payroll_indonesia.override.salary_slip.controller import (
    update_indonesia_tax_components,
    calculate_taxable_earnings
)
from payroll_indonesia.override.salary_slip.tax_calculator import (
    get_tax_status,
    is_december_calculation,
    get_ptkp_value,
    calculate_progressive_tax,
    get_ter_rate,
    get_ter_category,
    categorize_components_by_tax_effect
)


class SalarySlipIndonesia:
    """
    Salary Slip Indonesia class for extending Salary Slip functionality.
    """
    
    def __init__(self, salary_slip=None):
        """
        Initialize with optional salary slip document.
        
        Args:
            salary_slip: Salary Slip document
        """
        self.doc = salary_slip
    
    def validate_tax_settings(self):
        """
        Validate tax-related settings.
        """
        try:
            if not self.doc:
                return
            
            # Skip if Indonesia payroll not enabled
            if cint(getattr(self.doc, "calculate_indonesia_tax", 0)) != 1:
                return
            
            # Validate tax status
            tax_status = get_tax_status(self.doc)
            if not tax_status:
                frappe.throw(_("Tax status (PTKP) must be set for Indonesia tax calculation."))
            
            # Validate tax method
            tax_method = getattr(self.doc, "tax_method", "Progressive")
            if tax_method not in ["Progressive", "TER"]:
                frappe.throw(_("Invalid tax method. Must be 'Progressive' or 'TER'."))
            
            # Validate components have tax effects defined
            self._validate_component_tax_effects()
            
            logger.debug(f"Tax settings validated for slip {getattr(self.doc, 'name', 'unknown')}")
        
        except Exception as e:
            logger.exception(f"Error validating tax settings: {str(e)}")
    
    def _validate_component_tax_effects(self):
        """
        Validate that components have valid tax effects.
        """
        try:
            # Count components missing tax effects
            missing_effects = []
            
            # Check earnings
            if hasattr(self.doc, "earnings") and self.doc.earnings:
                for earning in self.doc.earnings:
                    component = earning.salary_component
                    tax_effect = get_component_tax_effect(component, "Earning")
                    
                    if not tax_effect and flt(earning.amount) > 0:
                        missing_effects.append(f"Earning: {component}")
            
            # Check deductions
            if hasattr(self.doc, "deductions") and self.doc.deductions:
                for deduction in self.doc.deductions:
                    component = deduction.salary_component
                    
                    # Skip PPh 21 component
                    if component == "PPh 21":
                        continue
                    
                    tax_effect = get_component_tax_effect(component, "Deduction")
                    
                    if not tax_effect and flt(deduction.amount) > 0:
                        missing_effects.append(f"Deduction: {component}")
            
            # Show warning if components are missing tax effects
            if missing_effects:
                warning_msg = _(
                    "The following components are missing tax effect settings. "
                    "They will be treated as non-taxable by default:\n{0}"
                ).format("\n".join(missing_effects))
                frappe.msgprint(warning_msg, title=_("Missing Tax Effect Settings"), indicator="orange")
        
        except Exception as e:
            logger.exception(f"Error validating component tax effects: {str(e)}")
    
    def calculate_taxable_income(self):
        """
        Calculate taxable income based on tax effect types.
        
        Returns:
            float: Taxable income amount
        """
        try:
            if not self.doc:
                return 0.0
            
            # Use categorize_components_by_tax_effect to get taxable components
            tax_components = categorize_components_by_tax_effect(self.doc)
            
            # Sum objek pajak components and taxable natura
            taxable_income = tax_components["totals"].get(TAX_OBJEK_EFFECT, 0)
            taxable_income += tax_components["totals"].get(NATURA_OBJEK_EFFECT, 0)
            
            return flt(taxable_income, 2)
        
        except Exception as e:
            logger.exception(f"Error calculating taxable income: {str(e)}")
            return 0.0
    
    def is_december_calculation(self):
        """
        Check if this is a December calculation.
        
        Returns:
            bool: True if December calculation
        """
        return is_december_calculation(self.doc) if self.doc else False
    
    def calculate_pph21(self):
        """
        Calculate PPh 21 tax.
        
        Returns:
            float: Calculated PPh 21 amount
        """
        try:
            if not self.doc:
                return 0.0
            
            # Skip if Indonesia payroll not enabled
            if cint(getattr(self.doc, "calculate_indonesia_tax", 0)) != 1:
                return 0.0
            
            # Get tax method
            tax_method = getattr(self.doc, "tax_method", "Progressive")
            
            # Calculate tax based on method
            if tax_method == "TER":
                return self._calculate_pph21_ter()
            elif self.is_december_calculation():
                return self._calculate_pph21_december()
            else:
                return self._calculate_pph21_progressive()
        
        except Exception as e:
            logger.exception(f"Error calculating PPh 21: {str(e)}")
            return 0.0
    
    def _calculate_pph21_progressive(self):
        """
        Calculate PPh 21 using progressive method.
        
        Returns:
            float: Calculated tax amount
        """
        try:
            # Get tax status and PTKP value
            tax_status = get_tax_status(self.doc)
            annual_ptkp = get_ptkp_value(tax_status)
            
            # Get taxable income
            monthly_taxable = self.calculate_taxable_income()
            annual_taxable = monthly_taxable * MONTHS_PER_YEAR
            
            # Get tax components by effect
            tax_components = categorize_components_by_tax_effect(self.doc)
            
            # Calculate biaya jabatan (5% of annual taxable, capped monthly)
            biaya_jabatan = min(
                annual_taxable * 0.05,
                BIAYA_JABATAN_MAX * MONTHS_PER_YEAR,
            )
            
            # Sum tax deductions (annualized)
            tax_deductions = tax_components["totals"].get(TAX_DEDUCTION_EFFECT, 0) * MONTHS_PER_YEAR
            
            # Calculate PKP (taxable income after deductions)
            annual_pkp = max(0, annual_taxable - biaya_jabatan - tax_deductions - annual_ptkp)
            
            # Round PKP down to nearest 1000
            annual_pkp = flt(annual_pkp, 0)
            annual_pkp = annual_pkp - (annual_pkp % 1000)
            
            # Calculate tax using progressive method
            annual_tax, _ = calculate_progressive_tax(annual_pkp)
            
            # Convert to monthly tax
            monthly_tax = annual_tax / MONTHS_PER_YEAR
            
            # Store calculation details
            if hasattr(self.doc, "ptkp_value"):
                self.doc.ptkp_value = annual_ptkp
            if hasattr(self.doc, "monthly_taxable"):
                self.doc.monthly_taxable = monthly_taxable
            if hasattr(self.doc, "annual_taxable_income"):
                self.doc.annual_taxable_income = annual_taxable
            if hasattr(self.doc, "biaya_jabatan"):
                self.doc.biaya_jabatan = biaya_jabatan
            if hasattr(self.doc, "tax_deductions"):
                self.doc.tax_deductions = tax_deductions
            if hasattr(self.doc, "annual_pkp"):
                self.doc.annual_pkp = annual_pkp
            if hasattr(self.doc, "annual_tax"):
                self.doc.annual_tax = annual_tax
            
            return flt(monthly_tax, 2)
        
        except Exception as e:
            logger.exception(f"Error calculating progressive PPh 21: {str(e)}")
            return 0.0
    
    def _calculate_pph21_december(self):
        """
        Calculate PPh 21 for December (year-end adjustment).
        
        Returns:
            float: Calculated tax amount
        """
        try:
            # Get YTD values
            ytd_gross = flt(getattr(self.doc, "ytd_gross_pay", 0))
            ytd_bpjs = flt(getattr(self.doc, "ytd_bpjs", 0))
            ytd_pph21 = flt(getattr(self.doc, "ytd_pph21", 0))
            
            # Get current month taxable income
            monthly_taxable = self.calculate_taxable_income()
            
            # Get tax status and PTKP value
            tax_status = get_tax_status(self.doc)
            annual_ptkp = get_ptkp_value(tax_status)
            
            # Get tax components by effect
            tax_components = categorize_components_by_tax_effect(self.doc)
            
            # Calculate total annual taxable income
            annual_taxable = ytd_gross + monthly_taxable
            
            # Calculate biaya jabatan (5% of annual taxable, capped monthly)
            biaya_jabatan = min(
                annual_taxable * 0.05,
                BIAYA_JABATAN_MAX * MONTHS_PER_YEAR,
            )
            
            # Calculate tax deductions (YTD BPJS + current month tax deductions)
            current_deductions = tax_components["totals"].get(TAX_DEDUCTION_EFFECT, 0)
            tax_deductions = ytd_bpjs + current_deductions
            
            # Calculate PKP (taxable income after deductions)
            annual_pkp = max(0, annual_taxable - biaya_jabatan - tax_deductions - annual_ptkp)
            
            # Round PKP down to nearest 1000
            annual_pkp = flt(annual_pkp, 0)
            annual_pkp = annual_pkp - (annual_pkp % 1000)
            
            # Calculate tax using progressive method
            annual_tax, _ = calculate_progressive_tax(annual_pkp)
            
            # Calculate December tax (annual tax - YTD tax)
            december_tax = annual_tax - ytd_pph21
            
            # Store calculation details
            if hasattr(self.doc, "ptkp_value"):
                self.doc.ptkp_value = annual_ptkp
            if hasattr(self.doc, "monthly_taxable"):
                self.doc.monthly_taxable = monthly_taxable
            if hasattr(self.doc, "ytd_gross_pay"):
                self.doc.ytd_gross_pay = ytd_gross
            if hasattr(self.doc, "ytd_bpjs"):
                self.doc.ytd_bpjs = ytd_bpjs
            if hasattr(self.doc, "ytd_pph21"):
                self.doc.ytd_pph21 = ytd_pph21
            if hasattr(self.doc, "annual_taxable_income"):
                self.doc.annual_taxable_income = annual_taxable
            if hasattr(self.doc, "biaya_jabatan"):
                self.doc.biaya_jabatan = biaya_jabatan
            if hasattr(self.doc, "tax_deductions"):
                self.doc.tax_deductions = tax_deductions
            if hasattr(self.doc, "annual_pkp"):
                self.doc.annual_pkp = annual_pkp
            if hasattr(self.doc, "annual_tax"):
                self.doc.annual_tax = annual_tax
            if hasattr(self.doc, "december_tax"):
                self.doc.december_tax = december_tax
            
            return flt(december_tax, 2)
        
        except Exception as e:
            logger.exception(f"Error calculating December PPh 21: {str(e)}")
            return 0.0
    
    def _calculate_pph21_ter(self):
        """
        Calculate PPh 21 using TER method.
        
        Returns:
            float: Calculated tax amount
        """
        try:
            # Get tax status
            tax_status = get_tax_status(self.doc)
            
            # Get TER category based on tax status
            ter_category = get_ter_category(tax_status)
            
            # Get taxable income
            taxable_income = self.calculate_taxable_income()
            
            # Get TER rate based on category and income
            ter_rate = get_ter_rate(ter_category, taxable_income)
            
            # Calculate tax using TER method (simple multiplication)
            tax_amount = taxable_income * ter_rate
            
            # Store calculation details
            if hasattr(self.doc, "ter_category"):
                self.doc.ter_category = ter_category
            if hasattr(self.doc, "ter_rate"):
                self.doc.ter_rate = ter_rate * 100  # as percentage
            if hasattr(self.doc, "monthly_taxable"):
                self.doc.monthly_taxable = taxable_income
            
            return flt(tax_amount, 2)
        
        except Exception as e:
            logger.exception(f"Error calculating TER PPh 21: {str(e)}")
            return 0.0
