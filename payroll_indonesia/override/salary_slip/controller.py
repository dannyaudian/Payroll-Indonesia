# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
Salary Slip Controller module - Indonesia-specific logic for salary processing
"""

import logging
from typing import Dict, List, Tuple, Any, Optional, Union

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, date_diff, add_months

from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.config.config import get_component_tax_effect
from payroll_indonesia.constants import (
    TAX_DEDUCTION_EFFECT,
    TAX_OBJEK_EFFECT,
    TAX_NON_OBJEK_EFFECT,
    NATURA_OBJEK_EFFECT,
    NATURA_NON_OBJEK_EFFECT,
)
from payroll_indonesia.override.salary_slip.tax_calculator import (
    calculate_monthly_pph_progressive,
    calculate_december_pph,
    calculate_monthly_pph_with_ter,
    is_december_calculation,
    update_slip_fields,
)

__all__ = [
    "update_indonesia_tax_components",
    "calculate_taxable_earnings",
    "get_bpjs_deductions",
    "update_slip_with_tax_details",
    "process_indonesia_taxes",
]


def calculate_taxable_earnings(doc: Any) -> float:
    """
    Calculate taxable earnings based on component tax effect type.
    
    Args:
        doc: Salary Slip document
        
    Returns:
        float: Total taxable earnings
    """
    try:
        taxable_earnings = 0.0
        
        # Process earnings
        if hasattr(doc, "earnings") and doc.earnings:
            for earning in doc.earnings:
                component = earning.salary_component
                amount = flt(earning.amount)
                
                # Skip zero amounts
                if amount <= 0:
                    continue
                
                # Get tax effect for this component
                tax_effect = get_component_tax_effect(component, "Earning")
                
                # Add to taxable earnings if it's an objek pajak or taxable natura
                if tax_effect == TAX_OBJEK_EFFECT or tax_effect == NATURA_OBJEK_EFFECT:
                    taxable_earnings += amount
                    logger.debug(f"Added taxable earning: {component} = {amount}")
        
        logger.debug(f"Total taxable earnings: {taxable_earnings}")
        return taxable_earnings
    
    except Exception as e:
        logger.exception(f"Error calculating taxable earnings: {str(e)}")
        return 0.0


def get_bpjs_deductions(doc: Any) -> Dict[str, float]:
    """
    Get BPJS deductions based on tax effect type.
    
    Args:
        doc: Salary Slip document
        
    Returns:
        Dict[str, float]: Dictionary with BPJS deduction details
    """
    try:
        result = {
            "jht_employee": 0.0,
            "jp_employee": 0.0,
            "jkn_employee": 0.0,
            "total_employee": 0.0,
            "jht_employer": 0.0,
            "jp_employer": 0.0,
            "jkn_employer": 0.0,
            "jkk_employer": 0.0,
            "jkm_employer": 0.0,
            "total_employer": 0.0,
            "total_combined": 0.0,
        }
        
        # Process deductions
        if hasattr(doc, "deductions") and doc.deductions:
            for deduction in doc.deductions:
                component = deduction.salary_component
                amount = flt(deduction.amount)
                
                # Skip zero amounts
                if amount <= 0:
                    continue
                
                # Get tax effect for this component
                tax_effect = get_component_tax_effect(component, "Deduction")
                
                # Check if this is a tax deduction (BPJS is typically a tax deduction)
                if tax_effect == TAX_DEDUCTION_EFFECT:
                    # Categorize based on component name
                    # This still relies on component naming but with tax effect as first filter
                    component_lower = component.lower()
                    
                    if "jht" in component_lower and "employee" in component_lower:
                        result["jht_employee"] += amount
                        result["total_employee"] += amount
                    elif "jp" in component_lower and "employee" in component_lower:
                        result["jp_employee"] += amount
                        result["total_employee"] += amount
                    elif "jkn" in component_lower and "employee" in component_lower:
                        result["jkn_employee"] += amount
                        result["total_employee"] += amount
                    elif "jht" in component_lower and "employer" in component_lower:
                        result["jht_employer"] += amount
                        result["total_employer"] += amount
                    elif "jp" in component_lower and "employer" in component_lower:
                        result["jp_employer"] += amount
                        result["total_employer"] += amount
                    elif "jkn" in component_lower and "employer" in component_lower:
                        result["jkn_employer"] += amount
                        result["total_employer"] += amount
                    elif "jkk" in component_lower:
                        result["jkk_employer"] += amount
                        result["total_employer"] += amount
                    elif "jkm" in component_lower:
                        result["jkm_employer"] += amount
                        result["total_employer"] += amount
                    elif "bpjs" in component_lower:
                        # Generic BPJS component - add to employee portion
                        result["total_employee"] += amount
        
        # Calculate total
        result["total_combined"] = result["total_employee"] + result["total_employer"]
        
        return result
        
    except Exception as e:
        logger.exception(f"Error getting BPJS deductions: {str(e)}")
        return {
            "jht_employee": 0.0,
            "jp_employee": 0.0,
            "jkn_employee": 0.0,
            "total_employee": 0.0,
            "jht_employer": 0.0,
            "jp_employer": 0.0,
            "jkn_employer": 0.0,
            "jkk_employer": 0.0,
            "jkm_employer": 0.0,
            "total_employer": 0.0,
            "total_combined": 0.0,
        }


def update_slip_with_tax_details(doc: Any, details: Dict[str, Any]) -> None:
    """
    Update salary slip with tax calculation details.
    
    Args:
        doc: Salary Slip document
        details: Tax calculation details
    """
    try:
        # Update standard fields
        updates = {
            "tax_status": details.get("tax_status", ""),
            "ptkp_value": flt(details.get("ptkp_value", 0)),
            "monthly_taxable": flt(details.get("monthly_taxable", 0)),
            "annual_taxable": flt(details.get("annual_taxable", 0)),
        }
        
        # Add TER specific fields
        if "ter_category" in details:
            updates["ter_category"] = details.get("ter_category", "")
            updates["ter_rate"] = flt(details.get("ter_rate", 0))
        
        # Add progressive tax specific fields
        if "biaya_jabatan" in details:
            updates["biaya_jabatan"] = flt(details.get("biaya_jabatan", 0))
            updates["tax_deductions"] = flt(details.get("tax_deductions", 0))
            updates["annual_pkp"] = flt(details.get("annual_pkp", 0))
            updates["annual_tax"] = flt(details.get("annual_tax", 0))
        
        # Add December specific fields
        if "ytd_gross" in details:
            updates["ytd_gross"] = flt(details.get("ytd_gross", 0))
            updates["ytd_bpjs"] = flt(details.get("ytd_bpjs", 0))
            updates["ytd_pph21"] = flt(details.get("ytd_pph21", 0))
            updates["december_tax"] = flt(details.get("december_tax", 0))
        
        # Store tax bracket details as JSON
        if "tax_brackets" in details and details["tax_brackets"]:
            updates["tax_brackets_json"] = frappe.as_json(details["tax_brackets"])
        
        # Store component details as JSON
        if "components" in details and details["components"]:
            updates["tax_components_json"] = frappe.as_json(details["components"])
        
        # Update the document
        update_slip_fields(doc, updates)
        
    except Exception as e:
        logger.exception(f"Error updating slip with tax details: {str(e)}")


def process_indonesia_taxes(doc: Any) -> float:
    """
    Process Indonesia-specific tax calculations.
    
    Args:
        doc: Salary Slip document
        
    Returns:
        float: Calculated PPh 21 amount
    """
    try:
        # Skip if not enabled
        if not cint(getattr(doc, "calculate_indonesia_tax", 0)):
            logger.debug(f"Indonesia tax calculation not enabled for slip {getattr(doc, 'name', 'unknown')}")
            return 0.0
        
        # Get tax method
        tax_method = getattr(doc, "tax_method", "Progressive")
        logger.debug(f"Using tax method: {tax_method}")
        
        # Calculate based on method
        if tax_method == "TER":
            tax_amount, details = calculate_monthly_pph_with_ter(doc)
        elif is_december_calculation(doc):
            tax_amount, details = calculate_december_pph(doc)
        else:
            tax_amount, details = calculate_monthly_pph_progressive(doc)
        
        # Update slip with calculation details
        update_slip_with_tax_details(doc, details)
        
        logger.debug(f"Tax calculation result: {tax_amount}")
        return flt(tax_amount, 2)
        
    except Exception as e:
        logger.exception(f"Error processing Indonesia taxes: {str(e)}")
        return 0.0


def update_indonesia_tax_components(doc: Any) -> None:
    """
    Update tax components in the salary slip based on calculation.
    
    Args:
        doc: Salary Slip document
    """
    try:
        # Skip if not enabled
        if not cint(getattr(doc, "calculate_indonesia_tax", 0)):
            logger.debug(f"Indonesia tax calculation not enabled for slip {getattr(doc, 'name', 'unknown')}")
            return
        
        # Calculate tax
        tax_amount = process_indonesia_taxes(doc)
        
        # Check if PPh 21 component exists
        pph21_component = None
        
        # Look for component in deductions
        if hasattr(doc, "deductions") and doc.deductions:
            for deduction in doc.deductions:
                if deduction.salary_component == "PPh 21":
                    pph21_component = deduction
                    break
        
        # If not found, add it
        if not pph21_component:
            if not hasattr(doc, "deductions"):
                doc.deductions = []
            
            pph21_component = frappe.get_doc({
                "doctype": "Salary Detail",
                "parentfield": "deductions",
                "parenttype": "Salary Slip",
                "salary_component": "PPh 21",
                "abbr": "PPh21",
                "amount": 0
            })
            doc.append("deductions", pph21_component)
            logger.debug("Added PPh 21 component to deductions")
        
        # Update amount
        pph21_component.amount = tax_amount
        
        # Update total deductions
        if hasattr(doc, "compute_total_deductions"):
            doc.compute_total_deductions()
        
        # Update net pay
        if hasattr(doc, "compute_net_pay"):
            doc.compute_net_pay()
        
        logger.debug(f"Updated PPh 21 component with amount: {tax_amount}")
        
    except Exception as e:
        logger.exception(f"Error updating Indonesia tax components: {str(e)}")