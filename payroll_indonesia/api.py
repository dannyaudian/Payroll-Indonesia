# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:15:45 by dannyaudian

"""
Payroll Indonesia API endpoints.

Provides a thin API layer for accessing payroll functionality:
- Employee data
- Salary slip information
- Tax calculation
- BPJS calculation
"""

# Standard library imports
import json
import logging
from typing import Dict, Any, List, Optional, Union

# Frappe imports
import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

# Payroll Indonesia imports
from payroll_indonesia.config import get_live_config
from payroll_indonesia.override.salary_slip import (
    bpjs_calculator as bpjs_calc,
    tax_calculator as tax_calc,
    ter_calculator as ter_calc
)

logger = logging.getLogger('payroll_api')


@frappe.whitelist(allow_guest=False)
def get_employee(name: str = None, filters: str = None) -> Dict[str, Any]:
    """
    API to get employee data.
    
    Args:
        name: Employee ID
        filters: JSON string of filters
        
    Returns:
        dict: Employee data or list
    """
    try:
        if not frappe.has_permission("Employee", "read"):
            frappe.throw(_("Not permitted to read Employee data"), 
                        frappe.PermissionError)
        
        # Get specific employee
        if name:
            doc = frappe.get_doc("Employee", name)
            return {
                "status": "success",
                "data": doc
            }
        
        # Parse filters
        filter_dict = json.loads(filters) if isinstance(filters, str) else {}
        
        # Get filtered employees
        employees = frappe.get_all(
            "Employee",
            filters=filter_dict,
            fields=[
                "name", "employee_name", "company", "status", 
                "date_of_joining", "department", "designation",
                "status_pajak", "npwp", "golongan"
            ]
        )
        
        return {
            "status": "success",
            "count": len(employees),
            "data": employees
        }
    except Exception as e:
        logger.error(f"Error getting employee data: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist(allow_guest=False)
def calculate_bpjs(salary: float) -> Dict[str, Any]:
    """
    Calculate BPJS based on salary.
    
    Args:
        salary: Salary amount
        
    Returns:
        dict: BPJS calculation results
    """
    try:
        salary = flt(salary)
        if salary <= 0:
            frappe.throw(_("Salary must be greater than zero"))
        
        # Use bpjs_calculator to calculate components
        mock_doc = frappe._dict({"gross_pay": salary})
        result = bpjs_calc.calculate_components(mock_doc)
        
        return {
            "status": "success",
            "data": result
        }
    except Exception as e:
        logger.error(f"Error calculating BPJS: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist(allow_guest=False)
def calculate_tax(salary: float, tax_status: str = "TK0", 
                 method: str = "progressive") -> Dict[str, Any]:
    """
    Calculate PPh 21 tax based on salary.
    
    Args:
        salary: Salary amount
        tax_status: Tax status code (TK0, K1, etc.)
        method: Tax calculation method (progressive or ter)
        
    Returns:
        dict: Tax calculation results
    """
    try:
        salary = flt(salary)
        if salary <= 0:
            frappe.throw(_("Salary must be greater than zero"))
        
        # Create mock document
        mock_doc = frappe._dict({
            "gross_pay": salary,
            "total_bpjs": 0,
            "employee_doc": frappe._dict({"status_pajak": tax_status})
        })
        
        # Calculate based on method
        if method.lower() == "ter":
            result = ter_calc.calculate_monthly_pph_with_ter(mock_doc)
        else:
            result = tax_calc.calculate_monthly_pph_progressive(mock_doc)
        
        return {
            "status": "success",
            "data": result
        }
    except Exception as e:
        logger.error(f"Error calculating tax: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist(allow_guest=False)
def get_tax_brackets() -> Dict[str, Any]:
    """
    Get tax brackets from configuration.
    
    Returns:
        dict: Tax brackets
    """
    try:
        cfg = get_live_config()
        brackets = tax_calc.get_tax_brackets(cfg)
        
        return {
            "status": "success",
            "data": brackets
        }
    except Exception as e:
        logger.error(f"Error getting tax brackets: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist(allow_guest=False)
def get_ter_rates() -> Dict[str, Any]:
    """
    Get TER rates from configuration.
    
    Returns:
        dict: TER rates by category
    """
    try:
        cfg = get_live_config()
        
        # Get TER rates
        ter_rates = cfg.get("ter_rates", {})
        
        return {
            "status": "success",
            "data": ter_rates
        }
    except Exception as e:
        logger.error(f"Error getting TER rates: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist(allow_guest=False)
def get_salary_slip(name: str) -> Dict[str, Any]:
    """
    Get salary slip details.
    
    Args:
        name: Salary slip ID
        
    Returns:
        dict: Salary slip details
    """
    try:
        if not frappe.has_permission("Salary Slip", "read"):
            frappe.throw(_("Not permitted to read Salary Slip data"), 
                        frappe.PermissionError)
        
        # Get salary slip
        slip = frappe.get_doc("Salary Slip", name)
        
        # Extract key information
        result = {
            "name": slip.name,
            "employee": slip.employee,
            "employee_name": slip.employee_name,
            "start_date": slip.start_date,
            "end_date": slip.end_date,
            "gross_pay": slip.gross_pay,
            "net_pay": slip.net_pay,
            "total_deduction": slip.total_deduction
        }
        
        # Add Indonesia-specific fields if they exist
        for field in ["total_bpjs", "biaya_jabatan", "netto", 
                     "is_using_ter", "ter_rate", "ter_category"]:
            if hasattr(slip, field):
                result[field] = getattr(slip, field)
        
        # Add components
        if hasattr(slip, "earnings"):
            result["earnings"] = [
                {"component": e.salary_component, "amount": e.amount}
                for e in slip.earnings
            ]
        
        if hasattr(slip, "deductions"):
            result["deductions"] = [
                {"component": d.salary_component, "amount": d.amount}
                for d in slip.deductions
            ]
        
        return {
            "status": "success",
            "data": result
        }
    except Exception as e:
        logger.error(f"Error getting salary slip: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist(allow_guest=False)
def recalculate_tax(slip_name: str, method: str = None) -> Dict[str, Any]:
    """
    Recalculate tax for a salary slip.
    
    Args:
        slip_name: Salary slip ID
        method: Tax calculation method (progressive, ter, or december)
        
    Returns:
        dict: Recalculation results
    """
    try:
        if not frappe.has_permission("Salary Slip", "write"):
            frappe.throw(_("Not permitted to update Salary Slip data"), 
                        frappe.PermissionError)
        
        # Get salary slip
        slip = frappe.get_doc("Salary Slip", slip_name)
        
        # Check document status
        if slip.docstatus != 0:
            frappe.throw(_("Cannot recalculate tax for submitted or cancelled slip"))
        
        # Determine calculation method
        if method == "ter":
            slip.is_using_ter = 1
            result = ter_calc.calculate_monthly_pph_with_ter(slip)
        elif method == "december":
            slip.is_december_override = 1
            result = tax_calc.calculate_december_pph(slip)
        else:
            slip.is_using_ter = 0
            slip.is_december_override = 0
            result = tax_calc.calculate_monthly_pph_progressive(slip)
        
        # Save changes
        slip.save()
        
        return {
            "status": "success",
            "message": _("Tax recalculated successfully"),
            "data": result
        }
    except Exception as e:
        logger.error(f"Error recalculating tax: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist(allow_guest=False)
def get_bpjs_settings() -> Dict[str, Any]:
    """
    Get BPJS settings from configuration.
    
    Returns:
        dict: BPJS settings
    """
    try:
        cfg = get_live_config()
        bpjs_config = cfg.get("bpjs", {})
        
        return {
            "status": "success",
            "data": bpjs_config
        }
    except Exception as e:
        logger.error(f"Error getting BPJS settings: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }
