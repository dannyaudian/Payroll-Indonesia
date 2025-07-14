# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
Salary utilities module - Helper functions for salary processing
"""

import logging
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, date_diff

from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.config.config import get_component_tax_effect
from payroll_indonesia.constants import (
    TAX_DEDUCTION_EFFECT,
    TAX_OBJEK_EFFECT,
    TAX_NON_OBJEK_EFFECT,
    NATURA_OBJEK_EFFECT,
    NATURA_NON_OBJEK_EFFECT,
)

__all__ = [
    "calculate_ytd_and_ytm",
    "get_component_details",
    "get_component_amounts",
    "categorize_components_by_tax_effect",
]


def calculate_ytd_and_ytm(employee: str, date: Any) -> Dict[str, Dict[str, float]]:
    """
    Calculate year-to-date and year-to-month totals for an employee.
    
    Args:
        employee: Employee ID
        date: Reference date
        
    Returns:
        Dict: Dictionary containing YTD and YTM totals for gross pay, taxable, deductions, etc.
    """
    try:
        if not employee or not date:
            return {"ytd": {}, "ytm": {}}
        
        date_obj = getdate(date)
        year = date_obj.year
        month = date_obj.month
        
        # Initialize result
        result = {
            "ytd": {
                "gross": 0.0,
                "taxable": 0.0,
                "deductions": 0.0,
                "bpjs": 0.0,
                "pph21": 0.0,
                "net": 0.0
            },
            "ytm": {
                "gross": 0.0,
                "taxable": 0.0,
                "deductions": 0.0,
                "bpjs": 0.0,
                "pph21": 0.0,
                "net": 0.0
            }
        }
        
        # Query salary slips for this employee in current year
        slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": employee,
                "docstatus": 1,
                "posting_date": ["between", [f"{year}-01-01", f"{year}-12-31"]]
            },
            fields=[
                "name", "posting_date", "gross_pay", "total_deduction", "net_pay", 
                "tax_components_json", "pph21"
            ],
            order_by="posting_date"
        )
        
        # Process each slip
        for slip in slips:
            slip_date = getdate(slip.posting_date)
            slip_month = slip_date.month
            
            # Extract values
            gross = flt(slip.gross_pay)
            deductions = flt(slip.total_deduction)
            net = flt(slip.net_pay)
            pph21 = flt(slip.pph21) if hasattr(slip, "pph21") else 0.0
            
            # Get taxable income and BPJS from tax_components_json if available
            taxable = 0.0
            bpjs = 0.0
            
            if hasattr(slip, "tax_components_json") and slip.tax_components_json:
                try:
                    tax_components = frappe.parse_json(slip.tax_components_json)
                    if tax_components and isinstance(tax_components, dict):
                        # Extract taxable income (penambah_bruto)
                        if "total" in tax_components and "penambah_bruto" in tax_components["total"]:
                            taxable = flt(tax_components["total"]["penambah_bruto"])
                        
                        # Extract BPJS (assuming they're in pengurang_netto)
                        if "pengurang_netto" in tax_components:
                            for component, amount in tax_components["pengurang_netto"].items():
                                if "bpjs" in component.lower():
                                    bpjs += flt(amount)
                except Exception as e:
                    logger.warning(f"Error parsing tax_components_json: {str(e)}")
            
            # Add to YTD
            result["ytd"]["gross"] += gross
            result["ytd"]["taxable"] += taxable
            result["ytd"]["deductions"] += deductions
            result["ytd"]["bpjs"] += bpjs
            result["ytd"]["pph21"] += pph21
            result["ytd"]["net"] += net
            
            # Add to YTM if month <= reference month
            if slip_month <= month:
                result["ytm"]["gross"] += gross
                result["ytm"]["taxable"] += taxable
                result["ytm"]["deductions"] += deductions
                result["ytm"]["bpjs"] += bpjs
                result["ytm"]["pph21"] += pph21
                result["ytm"]["net"] += net
        
        return result
    
    except Exception as e:
        logger.exception(f"Error calculating YTD/YTM for {employee}: {str(e)}")
        return {"ytd": {}, "ytm": {}}


def get_component_details(slip: Any, component_name: str) -> Dict[str, Any]:
    """
    Get details for a specific component in a salary slip.
    
    Args:
        slip: Salary Slip document
        component_name: Name of the salary component
        
    Returns:
        Dict: Dictionary with component details
    """
    try:
        result = {
            "found": False,
            "type": None,
            "amount": 0.0,
            "tax_effect": None
        }
        
        # Check earnings
        if hasattr(slip, "earnings") and slip.earnings:
            for earning in slip.earnings:
                if earning.salary_component == component_name:
                    result["found"] = True
                    result["type"] = "Earning"
                    result["amount"] = flt(earning.amount)
                    result["tax_effect"] = get_component_tax_effect(component_name, "Earning")
                    return result
        
        # Check deductions
        if hasattr(slip, "deductions") and slip.deductions:
            for deduction in slip.deductions:
                if deduction.salary_component == component_name:
                    result["found"] = True
                    result["type"] = "Deduction"
                    result["amount"] = flt(deduction.amount)
                    result["tax_effect"] = get_component_tax_effect(component_name, "Deduction")
                    return result
        
        return result
    
    except Exception as e:
        logger.exception(f"Error getting component details for {component_name}: {str(e)}")
        return {"found": False, "type": None, "amount": 0.0, "tax_effect": None}


def get_component_amounts(slip: Any, component_names: List[str]) -> Dict[str, float]:
    """
    Get amounts for multiple components in a salary slip.
    
    Args:
        slip: Salary Slip document
        component_names: List of component names
        
    Returns:
        Dict: Dictionary with component names as keys and amounts as values
    """
    try:
        result = {}
        
        for component in component_names:
            details = get_component_details(slip, component)
            result[component] = details["amount"] if details["found"] else 0.0
        
        return result
    
    except Exception as e:
        logger.exception(f"Error getting component amounts: {str(e)}")
        return {}


def categorize_components_by_tax_effect(slip: Any) -> Dict[str, Dict[str, float]]:
    """
    Categorize components in a salary slip by their tax effect.
    
    Args:
        slip: Salary Slip document
        
    Returns:
        Dict: Dictionary with components categorized by tax effect
    """
    try:
        result = {
            TAX_OBJEK_EFFECT: {},
            TAX_DEDUCTION_EFFECT: {},
            TAX_NON_OBJEK_EFFECT: {},
            NATURA_OBJEK_EFFECT: {},
            NATURA_NON_OBJEK_EFFECT: {},
            "totals": {
                TAX_OBJEK_EFFECT: 0.0,
                TAX_DEDUCTION_EFFECT: 0.0,
                TAX_NON_OBJEK_EFFECT: 0.0,
                NATURA_OBJEK_EFFECT: 0.0,
                NATURA_NON_OBJEK_EFFECT: 0.0
            }
        }
        
        # Process earnings
        if hasattr(slip, "earnings") and slip.earnings:
            for earning in slip.earnings:
                component = earning.salary_component
                amount = flt(earning.amount)
                
                # Skip zero amounts
                if amount <= 0:
                    continue
                
                tax_effect = get_component_tax_effect(component, "Earning")
                
                # Default to non-taxable if not defined
                if not tax_effect:
                    tax_effect = TAX_NON_OBJEK_EFFECT
                
                if tax_effect not in result:
                    result[tax_effect] = {}
                    result["totals"][tax_effect] = 0.0
                
                result[tax_effect][component] = amount
                result["totals"][tax_effect] += amount
        
        # Process deductions
        if hasattr(slip, "deductions") and slip.deductions:
            for deduction in slip.deductions:
                component = deduction.salary_component
                amount = flt(deduction.amount)
                
                # Skip zero amounts
                if amount <= 0:
                    continue
                
                # Skip PPh 21 component
                if component == "PPh 21":
                    continue
                
                tax_effect = get_component_tax_effect(component, "Deduction")
                
                # Default to non-deductible if not defined
                if not tax_effect:
                    tax_effect = TAX_NON_OBJEK_EFFECT
                
                if tax_effect not in result:
                    result[tax_effect] = {}
                    result["totals"][tax_effect] = 0.0
                
                result[tax_effect][component] = amount
                result["totals"][tax_effect] += amount
        
        return result
    
    except Exception as e:
        logger.exception(f"Error categorizing components: {str(e)}")
        return {
            TAX_OBJEK_EFFECT: {},
            TAX_DEDUCTION_EFFECT: {},
            TAX_NON_OBJEK_EFFECT: {},
            NATURA_OBJEK_EFFECT: {},
            NATURA_NON_OBJEK_EFFECT: {},
            "totals": {
                TAX_OBJEK_EFFECT: 0.0,
                TAX_DEDUCTION_EFFECT: 0.0,
                TAX_NON_OBJEK_EFFECT: 0.0,
                NATURA_OBJEK_EFFECT: 0.0,
                NATURA_NON_OBJEK_EFFECT: 0.0
            }
        }