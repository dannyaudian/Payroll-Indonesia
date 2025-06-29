# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:34:41 by dannyaudian

"""
Helper functions for Salary Slip - without duplication.
"""

import logging
from typing import Any, Dict, Optional, List, Union, Tuple
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import getdate, flt, add_months

import payroll_indonesia.override.salary_slip.bpjs_calculator as bpjs_calc
import payroll_indonesia.override.salary_slip.tax_calculator as tax_calc
import payroll_indonesia.override.salary_slip.ter_calculator as ter_calc
from payroll_indonesia.config import get_live_config

logger = logging.getLogger(__name__)


def update_component_amount(slip: Any, component_name: str, amount: float) -> bool:
    """
    Update a salary component amount in the salary slip.
    
    Args:
        slip: Salary slip document
        component_name: Name of the salary component to update
        amount: New amount to set
        
    Returns:
        bool: True if component was found and updated, False otherwise
    """
    if not slip or not component_name:
        return False
    
    # Try to find component in earnings
    if hasattr(slip, "earnings"):
        for e in slip.earnings:
            if getattr(e, "salary_component", "") == component_name:
                e.amount = amount
                return True
    
    # Try to find component in deductions
    if hasattr(slip, "deductions"):
        for d in slip.deductions:
            if getattr(d, "salary_component", "") == component_name:
                d.amount = amount
                return True
    
    # Component not found
    logger.warning(
        f"Component {component_name} not found in slip {getattr(slip, 'name', 'unknown')}"
    )
    return False


def calculate_bpjs_components(slip: Any) -> Dict[str, float]:
    """
    Calculate BPJS components for a salary slip.
    This is a wrapper around bpjs_calculator.calculate_components with additional
    logic to update the salary slip document.
    
    Args:
        slip: Salary slip document
        
    Returns:
        Dict[str, float]: Calculated BPJS components
    """
    try:
        # Calculate components using the BPJS calculator
        components = bpjs_calc.calculate_components(slip)
        
        # Update the salary slip fields with calculated values
        _update_slip_bpjs_fields(slip, components)
        
        # Update BPJS component amounts in deductions
        _update_bpjs_component_amounts(slip, components)
        
        return components
    except Exception as e:
        logger.exception(f"Error calculating BPJS components: {e}")
        frappe.throw(_("Error calculating BPJS components: {0}").format(str(e)))


def _update_slip_bpjs_fields(slip: Any, components: Dict[str, float]) -> None:
    """
    Update the salary slip's BPJS fields with calculated component values.
    
    Args:
        slip: Salary slip document
        components: Dictionary of calculated BPJS components
    """
    # Update individual employee components
    if hasattr(slip, "kesehatan_employee"):
        slip.kesehatan_employee = components.get("kesehatan_employee", 0)
    
    if hasattr(slip, "jht_employee"):
        slip.jht_employee = components.get("jht_employee", 0)
    
    if hasattr(slip, "jp_employee"):
        slip.jp_employee = components.get("jp_employee", 0)
    
    # Update total BPJS amount
    if hasattr(slip, "total_bpjs"):
        slip.total_bpjs = components.get("total_employee", 0)


def _update_bpjs_component_amounts(slip: Any, components: Dict[str, float]) -> None:
    """
    Update BPJS component amounts in the salary slip deductions.
    
    Args:
        slip: Salary slip document
        components: Dictionary of calculated BPJS components
    """
    # Mapping of component names to BPJS calculation results
    component_mapping = {
        "BPJS Kesehatan Employee": "kesehatan_employee",
        "BPJS JHT Employee": "jht_employee",
        "BPJS JP Employee": "jp_employee"
    }
    
    # Update each component if it exists in the slip
    for component_name, calc_key in component_mapping.items():
        amount = components.get(calc_key, 0)
        update_component_amount(slip, component_name, amount)


def calculate_ytd_and_ytm(slip: Any, date: Optional[str] = None) -> Dict[str, float]:
    """
    Calculate Year-to-Date (YTD) and Year-to-Month (YTM) values for salary slip.
    
    Args:
        slip: Salary slip document
        date: Optional date to use instead of slip's end_date
        
    Returns:
        Dict with YTD and YTM values
    """
    try:
        # Use provided date or slip's end_date
        if not date and hasattr(slip, "end_date"):
            date = getattr(slip, "end_date")
        
        if not date:
            # If no date is available, use current date
            date = datetime.now().strftime("%Y-%m-%d")
        
        # Get employee ID
        employee = getattr(slip, "employee", None)
        if not employee:
            logger.warning("No employee found in salary slip")
            return _get_default_ytd_values()
        
        # Parse the date
        date_obj = getdate(date)
        year = date_obj.year
        month = date_obj.month
        
        # Get all salary slips for this employee in the current year up to the given month
        filters = {
            "employee": employee,
            "docstatus": 1,  # Submitted slips only
            "start_date": [">=", f"{year}-01-01"],
            "end_date": ["<=", f"{year}-{month:02d}-31"]
        }
        
        # Exclude current slip if it's in draft
        current_name = getattr(slip, "name", "")
        if current_name and getattr(slip, "docstatus", 0) == 0:  # Draft
            filters["name"] = ["!=", current_name]
        
        # Query salary slips
        slips = frappe.get_all(
            "Salary Slip",
            filters=filters,
            fields=[
                "gross_pay", "total_deduction", "total_bpjs", 
                "pph21", "name", "start_date"
            ]
        )
        
        # Calculate YTD totals
        ytd_gross = sum(flt(s.gross_pay) for s in slips)
        ytd_deductions = sum(flt(s.total_deduction) for s in slips)
        ytd_bpjs = sum(flt(s.total_bpjs) for s in slips)
        ytd_pph21 = sum(flt(s.pph21) for s in slips)
        
        # Calculate YTM (Year-to-Month but not including current month)
        # Get previous month
        prev_month_date = add_months(date_obj, -1)
        prev_month = prev_month_date.month
        
        # Filter slips for YTM (up to previous month)
        ytm_slips = [
            s for s in slips 
            if getdate(s.start_date).month <= prev_month
        ]
        
        ytm_gross = sum(flt(s.gross_pay) for s in ytm_slips)
        ytm_deductions = sum(flt(s.total_deduction) for s in ytm_slips)
        ytm_bpjs = sum(flt(s.total_bpjs) for s in ytm_slips)
        ytm_pph21 = sum(flt(s.pph21) for s in ytm_slips)
        
        # Create result dictionary
        result = {
            "ytd_gross": ytd_gross,
            "ytd_earnings": ytd_gross,  # Simplified as gross pay
            "ytd_deductions": ytd_deductions,
            "ytd_bpjs": ytd_bpjs,
            "ytd_pph21": ytd_pph21,
            "ytm_gross": ytm_gross,
            "ytm_earnings": ytm_gross,  # Simplified as gross pay
            "ytm_deductions": ytm_deductions,
            "ytm_bpjs": ytm_bpjs,
            "ytm_pph21": ytm_pph21,
        }
        
        return result
    except Exception as e:
        logger.exception(f"Error calculating YTD/YTM values: {e}")
        return _get_default_ytd_values()


def _get_default_ytd_values() -> Dict[str, float]:
    """
    Get default YTD and YTM values when calculation fails.
    
    Returns:
        Dict with default values (all zeros)
    """
    return {
        "ytd_gross": 0.0,
        "ytd_earnings": 0.0,
        "ytd_deductions": 0.0,
        "ytd_bpjs": 0.0,
        "ytd_pph21": 0.0,
        "ytm_gross": 0.0,
        "ytm_earnings": 0.0,
        "ytm_deductions": 0.0,
        "ytm_bpjs": 0.0,
        "ytm_pph21": 0.0,
    }


def apply_salary_structure_changes(slip: Any) -> None:
    """
    Apply any pending salary structure changes for the employee.
    
    Args:
        slip: Salary slip document
    """
    try:
        # Get configuration for auto-applying changes
        cfg = get_live_config()
        auto_apply = cfg.get("salary", {}).get("auto_apply_changes", 0)
        
        if not auto_apply:
            return
        
        employee = getattr(slip, "employee", None)
        if not employee:
            return
        
        # Get slip's start and end dates
        start_date = getattr(slip, "start_date", None)
        end_date = getattr(slip, "end_date", None)
        
        if not start_date or not end_date:
            return
        
        # Get pending salary structure changes
        filters = {
            "employee": employee,
            "docstatus": 1,  # Submitted only
            "effective_date": ["between", [start_date, end_date]],
            "applied": 0  # Not applied yet
        }
        
        pending_changes = frappe.get_all(
            "Salary Structure Change",
            filters=filters,
            fields=["name", "effective_date", "component", "amount", "type"]
        )
        
        # Apply each pending change
        for change in pending_changes:
            component = change.get("component")
            amount = flt(change.get("amount"))
            change_type = change.get("type", "absolute")
            
            if not component:
                continue
            
            # Get current amount from slip
            current_amount = _get_component_amount(slip, component)
            
            # Calculate new amount based on change type
            if change_type == "percentage":
                new_amount = current_amount * (1 + amount / 100)
            else:  # absolute
                new_amount = amount
            
            # Update component in slip
            if update_component_amount(slip, component, new_amount):
                # Mark change as applied
                frappe.db.set_value("Salary Structure Change", change.name, "applied", 1)
                logger.info(
                    f"Applied salary structure change {change.name} for {employee}: "
                    f"{component} = {new_amount}"
                )
    except Exception as e:
        logger.exception(f"Error applying salary structure changes: {e}")
        # Don't throw, just log the error to avoid breaking slip creation


def _get_component_amount(slip: Any, component_name: str) -> float:
    """
    Get the current amount of a salary component in the slip.
    
    Args:
        slip: Salary slip document
        component_name: Name of the salary component
        
    Returns:
        float: Current amount of the component, or 0 if not found
    """
    # Check earnings
    if hasattr(slip, "earnings"):
        for e in slip.earnings:
            if getattr(e, "salary_component", "") == component_name:
                return flt(getattr(e, "amount", 0))
    
    # Check deductions
    if hasattr(slip, "deductions"):
        for d in slip.deductions:
            if getattr(d, "salary_component", "") == component_name:
                return flt(getattr(d, "amount", 0))
    
    return 0.0
