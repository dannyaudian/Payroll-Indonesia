# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
Payroll Controller module - Indonesia-specific logic for payroll processing
"""

import logging
from typing import Dict, List, Tuple, Any, Optional

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate

from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.config.config import get_component_tax_effect
from payroll_indonesia.constants import (
    TAX_DEDUCTION_EFFECT,
    TAX_OBJEK_EFFECT,
    TAX_NON_OBJEK_EFFECT,
    NATURA_OBJEK_EFFECT,
    NATURA_NON_OBJEK_EFFECT,
)
from payroll_indonesia.override.salary_slip.controller import (
    update_indonesia_tax_components,
    calculate_taxable_earnings,
    ensure_employee_tax_summary_integration,
)

__all__ = [
    "validate_salary_slip",
    "calculate_tax",
    "process_indonesia_payroll",
]


def validate_salary_slip(doc: Any) -> None:
    """
    Validate salary slip for Indonesia-specific requirements.
    
    Args:
        doc: Salary Slip document
    """
    try:
        # Skip if not enabled
        if not cint(getattr(doc, "calculate_indonesia_tax", 0)):
            logger.debug(f"Indonesia tax validation not enabled for slip {getattr(doc, 'name', 'unknown')}")
            return
        
        # Validate tax status is set
        tax_status = getattr(doc, "status_pajak", None)
        if not tax_status:
            # Try to get from employee
            employee = getattr(doc, "employee_doc", None)
            if not employee and hasattr(doc, "employee"):
                try:
                    employee = frappe.get_doc("Employee", doc.employee)
                    doc.employee_doc = employee
                except Exception:
                    pass
            
            if employee and hasattr(employee, "status_pajak") and employee.status_pajak:
                doc.status_pajak = employee.status_pajak
                logger.debug(f"Set tax status to {doc.status_pajak} from employee")
            else:
                frappe.msgprint(_("Tax status (PTKP) not set for employee. Using default TK0."))
                doc.status_pajak = "TK0"
        
        # Validate tax method
        tax_method = getattr(doc, "tax_method", None)
        if not tax_method:
            doc.tax_method = "Progressive"
        elif tax_method not in ["Progressive", "TER"]:
            frappe.throw(_("Invalid tax method. Must be 'Progressive' or 'TER'."))
        
        # Validate TER category if using TER method
        if tax_method == "TER":
            ter_category = getattr(doc, "ter_category", None)
            if not ter_category:
                # Will be set by tax calculation
                pass
            elif ter_category not in ["TER A", "TER B", "TER C"]:
                frappe.throw(_("Invalid TER category. Must be 'TER A', 'TER B', or 'TER C'."))
        
        # Validate earnings and deductions have proper tax effects
        _validate_component_tax_effects(doc)
    
    except Exception as e:
        logger.exception(f"Error validating salary slip: {str(e)}")


def _validate_component_tax_effects(doc: Any) -> None:
    """
    Validate that components have valid tax effects.
    
    Args:
        doc: Salary Slip document
    """
    try:
        # Check earnings
        if hasattr(doc, "earnings") and doc.earnings:
            for earning in doc.earnings:
                component = earning.salary_component
                tax_effect = get_component_tax_effect(component, "Earning")
                
                # Log warning for unknown tax effects
                if not tax_effect:
                    logger.warning(
                        f"Earning component '{component}' has no tax effect defined. "
                        f"Treated as non-taxable."
                    )
        
        # Check deductions
        if hasattr(doc, "deductions") and doc.deductions:
            for deduction in doc.deductions:
                component = deduction.salary_component
                tax_effect = get_component_tax_effect(component, "Deduction")
                
                # Log warning for unknown tax effects
                if not tax_effect:
                    logger.warning(
                        f"Deduction component '{component}' has no tax effect defined. "
                        f"Treated as non-deductible."
                    )
                
                # Special check for PPh 21 component
                if component == "PPh 21" and tax_effect != TAX_NON_OBJEK_EFFECT:
                    logger.warning(
                        "PPh 21 component should have 'Tidak Berpengaruh ke Pajak' tax effect. "
                        "Updating component setting recommended."
                    )
    
    except Exception as e:
        logger.exception(f"Error validating component tax effects: {str(e)}")


def calculate_tax(doc: Any) -> float:
    """
    Calculate income tax for Indonesia.
    
    Args:
        doc: Salary Slip document
        
    Returns:
        float: Calculated tax amount
    """
    try:
        # This is a wrapper that calls the controller function
        return update_indonesia_tax_components(doc)
    
    except Exception as e:
        logger.exception(f"Error calculating tax: {str(e)}")
        return 0.0


def process_indonesia_payroll(doc: Any) -> None:
    """
    Process Indonesia-specific payroll calculations.
    
    Args:
        doc: Salary Slip document
    """
    try:
        # Skip if not enabled
        if not cint(getattr(doc, "calculate_indonesia_tax", 0)):
            logger.debug(f"Indonesia payroll processing not enabled for slip {getattr(doc, 'name', 'unknown')}")
            return
        
        # Validate first
        validate_salary_slip(doc)
        
        # Calculate tax components
        calculate_tax(doc)

        # Set taxable earnings for reporting
        doc.taxable_earnings = calculate_taxable_earnings(doc)

        ensure_employee_tax_summary_integration(doc)

        logger.debug(f"Processed Indonesia payroll for slip {getattr(doc, 'name', 'unknown')}")
    
    except Exception as e:
        logger.exception(f"Error processing Indonesia payroll: {str(e)}")
