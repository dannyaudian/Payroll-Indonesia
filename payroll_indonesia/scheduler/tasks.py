# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:18:44 by dannyaudian

"""
Scheduler tasks for Payroll Indonesia.

This module contains scheduler tasks that should be registered in hooks.py:

scheduler_events = {
    "daily": ["payroll_indonesia.scheduler.tasks.daily_job"],
    "monthly": ["payroll_indonesia.scheduler.tasks.monthly_job"],
    "yearly": ["payroll_indonesia.scheduler.tasks.yearly_job"]
}
"""

import logging
import frappe
from frappe import _
from frappe.utils import cint
from frappe.utils import getdate, add_months, get_first_day, get_last_day, add_days
import payroll_indonesia.utilities.cache_utils as cache_utils
from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.config.config import doctype_defined

__all__ = ["daily_job", "monthly_job", "yearly_job", "validate_tax_cache"]

logger = logging.getLogger(__name__)


def daily_job():
    """
    Daily scheduler task for Payroll Indonesia.
    - Checks BPJS settings and account mappings
    - Validates cache for tax calculations
    - Monitors tax correction status
    """
    try:
        logger.info("Starting Payroll Indonesia daily tasks")

        # Check BPJS settings for each company
        check_bpjs_settings()

        # Enqueue tax cache validation (can be heavy)
        frappe.enqueue(
            "payroll_indonesia.scheduler.tasks.validate_tax_cache",
            queue="long",
            job_name="validate_tax_cache",
            is_async=True,
            timeout=1800,
        )

        logger.info("Completed Payroll Indonesia daily tasks")
    except Exception as e:
        logger.error(f"Error in daily_job: {str(e)}")
        frappe.log_error(f"Error in daily Payroll Indonesia task: {str(e)}")


def monthly_job():
    """
    Monthly scheduler task for Payroll Indonesia.
    - Creates BPJS payment summaries
    - Updates employee tax summaries for previous month
    - Generates tax reports
    """
    try:
        logger.info("Starting Payroll Indonesia monthly tasks")
        today = getdate()

        # Get previous month details
        prev_month = add_months(today, -1)
        month_num = prev_month.month
        year_num = prev_month.year

        # Create BPJS payment summaries
        create_bpjs_summaries(prev_month)

        # Update tax summaries for previous month (heavier task)
        frappe.enqueue(
            "payroll_indonesia.payroll_indonesia.tax.monthly_tasks.update_tax_summaries",
            queue="long",
            job_name="update_tax_summaries",
            month=month_num,
            year=year_num,
            is_async=True,
            timeout=3600,
        )

        logger.info("Completed Payroll Indonesia monthly tasks")
    except Exception as e:
        logger.error(f"Error in monthly_job: {str(e)}")
        frappe.log_error(f"Error in monthly Payroll Indonesia task: {str(e)}")


def yearly_job():
    """
    Yearly scheduler task for Payroll Indonesia.
    - Prepares annual tax reports
    - Processes December payroll runs
    - Generates Form 1721-A1
    """
    try:
        logger.info("Starting Payroll Indonesia yearly tasks")
        today = getdate()

        # Only run in January for previous year
        if today.month != 1:
            logger.info("Skipping yearly task - only runs in January")
            return

        prev_year = today.year - 1

        # Process December flagged runs
        frappe.enqueue(
            "payroll_indonesia.payroll_indonesia.tax.yearly_tasks.process_december_flagged_runs",
            queue="long",
            job_name="process_december_runs",
            year=prev_year,
            is_async=True,
            timeout=7200,
        )

        # Prepare tax reports (heaviest task)
        frappe.enqueue(
            "payroll_indonesia.payroll_indonesia.tax.yearly_tasks.prepare_tax_report",
            queue="long",
            job_name="prepare_tax_report",
            year=prev_year,
            is_async=True,
            timeout=7200,
        )

        logger.info("Completed Payroll Indonesia yearly tasks")
    except Exception as e:
        logger.error(f"Error in yearly_job: {str(e)}")
        frappe.log_error(f"Error in yearly Payroll Indonesia task: {str(e)}")


def check_bpjs_settings():
    """
    Check if BPJS Settings are properly configured in Payroll Indonesia Settings.

    Returns:
        bool: True if settings exist and are configured, False otherwise
    """
    if not doctype_defined("Payroll Indonesia Settings"):
        logger.warning("Payroll Indonesia Settings doctype not found")
        return False

    try:
        # For Single DocTypes, the correct approach is to use get_single
        settings = frappe.get_single("Payroll Indonesia Settings")

        # Check if essential BPJS settings are configured
        required_fields = [
            "kesehatan_employee_percent",
            "kesehatan_employer_percent",
            "jht_employee_percent",
            "jht_employer_percent",
            "jp_employee_percent",
            "jp_employer_percent",
            "jkk_percent",
            "jkm_percent",
        ]

        for field in required_fields:
            if not hasattr(settings, field) or not settings.get(field):
                logger.warning(f"Missing required BPJS setting: {field}")
                return False

        # Settings exist and are configured
        return True

    except Exception as e:
        logger.error(f"Error checking BPJS settings: {str(e)}")
        return False


def create_bpjs_summaries(date_obj=None):
    """Create monthly BPJS Payment Summaries"""
    try:
        # Get target month
        if not date_obj:
            today = getdate()
            date_obj = add_months(today, -1)  # Previous month

        # Get month date range
        first_day = get_first_day(date_obj)
        last_day = get_last_day(first_day)

        # Get all companies
        companies = frappe.get_all("Company", pluck="name")

        for company in companies:
            # Check if summary already exists
            existing = frappe.db.exists(
                "BPJS Payment Summary",
                {"company": company, "start_date": first_day, "end_date": last_day},
            )

            if not existing:
                try:
                    # Create new summary
                    summary = frappe.new_doc("BPJS Payment Summary")
                    summary.company = company
                    summary.start_date = first_day
                    summary.end_date = last_day
                    summary.generate_from_salary_slips()
                    summary.insert()

                    logger.info(f"Created BPJS Summary for {company} - {first_day}")
                except Exception as e:
                    logger.error(f"Error creating BPJS Summary for {company}: {str(e)}")
    except Exception as e:
        logger.error(f"Error in create_bpjs_summaries: {str(e)}")
        raise


def create_default_mapping(company):
    """Create default BPJS account mapping for a company"""
    try:
        mapping = frappe.new_doc("BPJS Account Mapping")
        mapping.company = company

        # Try to find default accounts
        # chart_of_accounts = frappe.db.get_value("Company", company, "chart_of_accounts")

        # Set default liability account
        default_payable = frappe.db.get_value("Company", company, "default_payable_account")
        if default_payable:
            mapping.kesehatan_account = default_payable
            mapping.jht_account = default_payable
            mapping.jp_account = default_payable
            mapping.jkk_account = default_payable
            mapping.jkm_account = default_payable

        mapping.insert()
        return mapping.name
    except Exception as e:
        logger.error(f"Error creating default mapping: {str(e)}")
        return None


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


def clear_caches():
    """Clear all payroll related caches"""
    try:
        cache_utils.clear_all_caches()
        logger.info("All payroll caches cleared successfully")
    except Exception as e:
        logger.warning(f"Error clearing all caches: {str(e)}")


def cleanup_logs():
    """Clean up old logs from the system"""
    # Placeholder for log cleanup logic
    pass