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

# from datetime import datetime

import frappe

# from frappe import _
from frappe.utils import getdate, add_months, get_first_day, get_last_day

# from payroll_indonesia.override.salary_slip import bpjs_calculator, tax_calculator
# from payroll_indonesia.payroll_indonesia import utils

logger = logging.getLogger("payroll_tasks")


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
    """Check BPJS settings and account mappings for all companies"""
    try:
        # Check if BPJS Settings exists
        if not frappe.db.exists("BPJS Settings", None):
            logger.warning("BPJS Settings not found")
            return

        # Get all companies
        companies = frappe.get_all("Company", pluck="name")

        for company in companies:
            # Check BPJS Account Mapping
            mapping = frappe.db.exists("BPJS Account Mapping", {"company": company})
            if not mapping:
                logger.warning(f"BPJS Account Mapping missing for company: {company}")

                # Create default mapping if possible
                try:
                    create_default_mapping(company)
                    logger.info(f"Created default BPJS mapping for: {company}")
                except Exception as e:
                    logger.error(f"Failed to create BPJS mapping for {company}: {str(e)}")
    except Exception as e:
        logger.error(f"Error checking BPJS settings: {str(e)}")
        raise


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


def validate_tax_cache():
    """Validate tax cache and clear if necessary"""
    try:
        # Clear cache for YTD totals older than 24 hours
        from payroll_indonesia.utilities.cache_utils import clear_pattern

        clear_pattern("ytd:*")
        clear_pattern("tax_summary:*")

        # Log cache clearing
        logger.info("Cleared tax calculation cache")
    except Exception as e:
        logger.error(f"Error validating tax cache: {str(e)}")
        raise


def clear_caches():
    # logika untuk menghapus cache
    pass


def cleanup_logs():
    # logika untuk membersihkan log
    pass
