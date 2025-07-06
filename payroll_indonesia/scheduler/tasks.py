# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Scheduler tasks for Payroll Indonesia.

This module contains scheduler tasks for tax cache validation.
These tasks should be registered in hooks.py:

scheduler_events = {
    "daily": ["payroll_indonesia.scheduler.tasks.validate_tax_cache"],
}
"""

import logging
import frappe
from frappe.utils import getdate, add_days
from payroll_indonesia.utilities import cache_utils

__all__ = ["validate_tax_cache"]

logger = logging.getLogger(__name__)


def validate_tax_cache() -> None:
    """
    Validate tax cache and rebuild if necessary.
    
    This function:
    1. Checks Employee Tax Summaries for consistency
    2. Rebuilds summaries with discrepancies
    3. Clears tax-related caches
    """
    try:
        logger.info("Starting tax cache validation")
        
        # Get all Employee Tax Summary docs modified since yesterday
        yesterday = add_days(getdate(), -1)
        tax_summaries = frappe.get_all(
            "Employee Tax Summary",
            filters={"modified": [">=", yesterday]},
            fields=["name", "employee", "tax_year"],
            limit=100  # Limit for performance reasons
        )
        
        # If no recent changes, check a sample of all summaries
        if not tax_summaries:
            tax_summaries = frappe.get_all(
                "Employee Tax Summary",
                fields=["name", "employee", "tax_year"],
                limit=50  # Sample size for validation
            )
        
        rebuild_count = 0
        
        for summary in tax_summaries:
            if validate_summary_consistency(summary.name, summary.employee, summary.tax_year):
                continue
                
            # If inconsistent, rebuild the summary
            rebuild_count += 1
            logger.warning(f"Tax summary {summary.name} inconsistent, rebuilding...")
            rebuild_tax_summary(summary.name)
            
            # Limit the number of rebuilds per run to avoid overloading
            if rebuild_count >= 10:
                logger.info("Reached rebuild limit, will continue in next run")
                break
        
        # Clear tax-related caches
        cache_patterns = ["tax_summary:*", "ytd:*", "salary_slip:tax:*"]
        for pattern in cache_patterns:
            cleared = cache_utils.clear_pattern(pattern)
            logger.info(f"Cleared {cleared or 0} cache keys with pattern '{pattern}'")
        
        logger.info(f"Tax cache validation completed. Rebuilt {rebuild_count} summaries.")
    except Exception as e:
        logger.error(f"Error in tax cache validation: {str(e)}")
        frappe.log_error(f"Error in tax cache validation: {str(e)}")


def validate_summary_consistency(summary_name: str, employee: str, tax_year: int) -> bool:
    """
    Validate that an Employee Tax Summary is consistent with its source data.
    
    Args:
        summary_name: Name of the Employee Tax Summary
        employee: Employee ID
        tax_year: Tax year of the summary
        
    Returns:
        bool: True if consistent, False if discrepancies found
    """
    try:
        # Get the monthly details from the summary
        monthly_details = frappe.get_all(
            "Employee Tax Monthly Detail",
            filters={"parent": summary_name},
            fields=["month", "total_taxable_income", "pph21"]
        )
        
        if not monthly_details:
            logger.debug(f"No monthly details found for {summary_name}")
            return False
        
        # Get corresponding salary slips
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": employee,
                "docstatus": 1,  # Submitted
                "posting_date": ["between", [f"{tax_year}-01-01", f"{tax_year}-12-31"]]
            },
            fields=["month(posting_date) as month", "total_taxable_income", "pph21_amount"]
        )
        
        # Create a map of month to salary slip data for easy comparison
        slip_map = {}
        for slip in salary_slips:
            month = slip.month
            if month not in slip_map:
                slip_map[month] = {
                    "total_taxable_income": 0,
                    "pph21_amount": 0
                }
            slip_map[month]["total_taxable_income"] += slip.total_taxable_income or 0
            slip_map[month]["pph21_amount"] += slip.pph21_amount or 0
        
        # Compare each monthly detail with corresponding salary slips
        for detail in monthly_details:
            month = detail.month
            if month not in slip_map:
                # Month in summary but no salary slips found
                return False
                
            # Check if amounts match with a small tolerance for rounding
            if (
                abs(detail.total_taxable_income - slip_map[month]["total_taxable_income"]) > 1 or
                abs(detail.pph21 - slip_map[month]["pph21_amount"]) > 1
            ):
                return False
                
        return True
    except Exception as e:
        logger.error(f"Error validating summary consistency for {summary_name}: {str(e)}")
        return False


def rebuild_tax_summary(summary_name: str) -> None:
    """
    Rebuild an Employee Tax Summary from source data.
    
    Args:
        summary_name: Name of the Employee Tax Summary to rebuild
    """
    try:
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
        
        # Clear existing monthly details
        summary.monthly_details = []
        
        # Get all salary slips for this employee in the tax year
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": summary.employee,
                "docstatus": 1,  # Submitted
                "posting_date": ["between", [f"{summary.tax_year}-01-01", f"{summary.tax_year}-12-31"]]
            },
            fields=["name", "posting_date", "total_taxable_income", "pph21_amount"]
        )
        
        # Group by month and rebuild monthly details
        month_data = {}
        for slip in salary_slips:
            month = slip.posting_date.month
            if month not in month_data:
                month_data[month] = {
                    "total_taxable_income": 0,
                    "pph21": 0
                }
            month_data[month]["total_taxable_income"] += slip.total_taxable_income or 0
            month_data[month]["pph21"] += slip.pph21_amount or 0
        
        # Create monthly details
        for month, data in month_data.items():
            summary.append("monthly_details", {
                "month": month,
                "total_taxable_income": data["total_taxable_income"],
                "pph21": data["pph21"]
            })
        
        # Update totals
        summary.total_taxable_income = sum(d["total_taxable_income"] for d in month_data.values())
        summary.total_tax = sum(d["pph21"] for d in month_data.values())
        
        # Save the updated summary
        summary.save()
        logger.info(f"Successfully rebuilt tax summary {summary_name}")
        
        # Clear specific cache for this summary
        cache_utils.clear_key(f"tax_summary:{summary.employee}:{summary.tax_year}")
        
    except Exception as e:
        logger.error(f"Error rebuilding tax summary {summary_name}: {str(e)}")