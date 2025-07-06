# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Functions for Salary Slip customization for Indonesian payroll.

These functions handle component updates, calculations, and post-submit operations.
"""

from typing import Any, Dict, List, Optional

import frappe
import logging
from frappe.utils import flt

from payroll_indonesia.payroll_indonesia import utils as pi_utils
from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter

# Initialize logger
logger = logging.getLogger(__name__)

# Define employer BPJS components
EMPLOYER_COMPONENTS = (
    "BPJS Kesehatan Employer",
    "BPJS JHT Employer",
    "BPJS JP Employer",
    "BPJS JKK",
    "BPJS JKM",
)

# Define public API
__all__ = [
    "update_tax_summary",
    "update_employee_history",  # alias
    "update_component_amount",
    "salary_slip_post_submit",
]


def update_component_amount(doc, method: Optional[str] = None) -> None:
    """
    Update salary component amounts based on Indonesian tax and BPJS regulations.

    This function handles all special component calculations for both earnings and deductions.
    Designed to be used as a doc event hook in Salary Slip.

    Args:
        doc: The Salary Slip document
        method: The method that triggered this hook (unused)
    """
    logger.debug(f"Updating component amounts for Salary Slip {doc.name}")
    
    # Calculate gross pay if not already set
    if not doc.gross_pay:
        doc.gross_pay = sum(flt(earning.amount) for earning in doc.earnings)
    
    # Determine TER eligibility
    settings = frappe.get_cached_doc("Payroll Indonesia Settings")
    is_ter_employee = str(getattr(doc, "status_pajak", "")).upper().startswith("TER")
    
    if settings.tax_calculation_method == "TER" and settings.use_ter and is_ter_employee:
        doc.using_ter = 1
        calculate_monthly_pph_with_ter(doc)
        logger.info(f"TER method applied for {doc.name}")
    else:
        doc.using_ter = 0
        _run_progressive_tax(doc)
        logger.info(f"Progressive method applied for {doc.name}")
    
    # Update BPJS deductions
    _update_bpjs_deductions(doc)
    
    # Update tax summary
    update_tax_summary(doc)
    
    # Recalculate totals to ensure net pay is refreshed
    doc.calculate_totals()
    logger.debug(f"Component update completed for Salary Slip {doc.name}")


def _run_progressive_tax(doc) -> None:
    """
    Run progressive tax calculation for non-TER employees.

    Args:
        doc: The Salary Slip document
    """
    try:
        from payroll_indonesia.override.salary_slip.tax_calculator import (
            calculate_monthly_pph_progressive
        )
        
        # Check if December override is needed
        if getattr(doc, "is_december_override", 0):
            from payroll_indonesia.override.salary_slip.tax_calculator import (
                calculate_december_pph
            )
            result = calculate_december_pph(doc)
            tax_amount = result.get("correction", 0.0)
        else:
            result = calculate_monthly_pph_progressive(doc)
            tax_amount = result.get("monthly_tax", 0.0)
        
        # Update PPh 21 component
        _update_component_amount(doc, "PPh 21", tax_amount)
        
        # Store in doc.pph21 for easier access
        doc.pph21 = tax_amount
        logger.debug(f"Calculated progressive tax: {tax_amount} for {doc.name}")
        
    except Exception as e:
        logger.exception(f"Error calculating progressive tax for {doc.name}: {e}")


def _update_bpjs_deductions(doc) -> None:
    """
    Update BPJS deduction components in the salary slip.
    
    Args:
        doc: The Salary Slip document
    """
    try:
        # Get BPJS configuration
        from payroll_indonesia.config.config import get_live_config
        config = get_live_config()
        bpjs_config = config.get("bpjs", {})
        
        # Calculate BPJS values based on gross pay
        base_salary = flt(doc.gross_pay) or 0
        kesehatan_max = flt(bpjs_config.get("kesehatan_max_salary", 12000000))
        jp_max = flt(bpjs_config.get("jp_max_salary", 9077600))
        
        # Employee components
        kesehatan_employee = pi_utils.calculate_bpjs(
            base_salary, 
            bpjs_config.get("kesehatan_employee_percent", 1.0),
            max_salary=kesehatan_max
        )
        
        jht_employee = pi_utils.calculate_bpjs(
            base_salary, 
            bpjs_config.get("jht_employee_percent", 2.0)
        )
        
        jp_employee = pi_utils.calculate_bpjs(
            base_salary,
            bpjs_config.get("jp_employee_percent", 1.0),
            max_salary=jp_max
        )
        
        # Update deduction components
        _update_component_amount(doc, "BPJS Kesehatan Employee", kesehatan_employee)
        _update_component_amount(doc, "BPJS JHT Employee", jht_employee)
        _update_component_amount(doc, "BPJS JP Employee", jp_employee)
        
        # Store in custom fields for easier access
        doc.kesehatan_employee = kesehatan_employee
        doc.jht_employee = jht_employee
        doc.jp_employee = jp_employee
        doc.total_bpjs = kesehatan_employee + jht_employee + jp_employee
        
        logger.debug(f"Updated BPJS deductions for {doc.name}: total={doc.total_bpjs}")
        
    except Exception as e:
        logger.exception(f"Error updating BPJS deductions for {doc.name}: {e}")


def _update_component_amount(doc, component_name: str, amount: float) -> None:
    """
    Update the amount of a salary component in deductions.
    
    Args:
        doc: The Salary Slip document
        component_name: Name of the salary component
        amount: Amount to set
    """
    if not hasattr(doc, "deductions"):
        return
    
    for deduction in doc.deductions:
        if deduction.salary_component == component_name:
            deduction.amount = amount
            logger.debug(f"Updated {component_name}: {amount}")
            break


def _get_component_amount(doc, component_name: str) -> float:
    """
    Get the amount of a salary component from deductions.
    
    Args:
        doc: The Salary Slip document
        component_name: Name of the salary component
        
    Returns:
        float: Amount of the component, 0 if not found
    """
    if not hasattr(doc, "deductions"):
        return 0.0
    
    for deduction in doc.deductions:
        if deduction.salary_component == component_name:
            return flt(deduction.amount)
    
    return 0.0


def _get_or_create_tax_row(slip) -> Any:
    """
    Get or create a tax summary row for the salary slip.
    
    Args:
        slip: The Salary Slip document
        
    Returns:
        Child row in Employee Tax Summary
    """
    # Fetch or create parent Employee Tax Summary
    employee = slip.employee
    company = slip.company
    fiscal_year = slip.fiscal_year
    
    filters = {
        "employee": employee,
        "company": company,
        "fiscal_year": fiscal_year
    }
    
    summary_name = frappe.db.get_value("Employee Tax Summary", filters)
    
    if summary_name:
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
    else:
        summary = frappe.new_doc("Employee Tax Summary")
        summary.employee = employee
        summary.company = company
        summary.fiscal_year = fiscal_year
    
    # Find or create the monthly detail row
    month = slip.month
    row = None
    
    for detail in summary.monthly_details:
        if detail.month == month:
            row = detail
            break
    
    if not row:
        row = summary.append("monthly_details", {
            "month": month,
            "taxable_income": 0,
            "tax_withheld": 0,
            "bpjs_employer_share": 0
        })
    
    return row, summary


def update_tax_summary(slip) -> None:
    """
    Update Employee Tax Summary with salary slip data.
    
    Args:
        slip: The Salary Slip document
    """
    if not slip.employee or not slip.company:
        return
    
    try:
        # Get or create tax summary row
        row, parent = _get_or_create_tax_row(slip)
        
        # Update taxable income and tax withheld
        row.taxable_income = flt(slip.gross_pay) or 0
        row.tax_withheld = _get_component_amount(slip, "PPh 21")
        
        # Calculate employer BPJS share
        employer_share = sum(
            _get_component_amount(slip, component) for component in EMPLOYER_COMPONENTS
        )
        
        # Update employer share
        row.bpjs_employer_share = employer_share
        
        # Save the documents
        parent.save(ignore_permissions=True)
        
        logger.info(
            f"Tax summary updated for {slip.employee} - {row.month}/{parent.fiscal_year}"
        )
        
    except Exception as e:
        logger.exception(f"Error updating tax summary for {slip.employee}: {e}")


def salary_slip_post_submit(doc, method: Optional[str] = None) -> None:
    """
    Process salary slip after submission.

    Updates employee tax summary records.

    Args:
        doc: The Salary Slip document
        method: The method that triggered this hook (unused)
    """
    logger.debug(f"Processing post-submit for Salary Slip {doc.name}")
    
    try:
        # Update tax summary
        update_tax_summary(doc)
        logger.debug(f"Post-submit processing completed for {doc.name}")
    
    except Exception as e:
        logger.exception(f"Error in post-submit processing for {doc.name}: {e}")


# Alias for backward compatibility
update_employee_history = update_tax_summary