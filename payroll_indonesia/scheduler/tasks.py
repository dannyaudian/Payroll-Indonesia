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
from frappe.utils import getdate, add_months, get_first_day, get_last_day, add_days
import payroll_indonesia.utilities.cache_utils as cache_utils
from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.config.config import doctype_defined
from typing import Optional, Dict, Any

__all__ = ["daily_job", "monthly_job", "yearly_job", "validate_tax_cache"]

logger = logging.getLogger(__name__)


def daily_job():
    try:
        logger.info("Starting Payroll Indonesia daily tasks")
        check_bpjs_settings()
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
    try:
        logger.info("Starting Payroll Indonesia monthly tasks")
        today = getdate()
        prev_month = add_months(today, -1)
        month_num = prev_month.month
        year_num = prev_month.year
        create_bpjs_summaries(prev_month)
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
    try:
        logger.info("Starting Payroll Indonesia yearly tasks")
        today = getdate()
        if today.month != 1:
            logger.info("Skipping yearly task - only runs in January")
            return
        prev_year = today.year - 1
        frappe.enqueue(
            "payroll_indonesia.payroll_indonesia.tax.yearly_tasks.process_december_flagged_runs",
            queue="long",
            job_name="process_december_runs",
            year=prev_year,
            is_async=True,
            timeout=7200,
        )
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
    if not doctype_defined("Payroll Indonesia Settings"):
        logger.warning("Payroll Indonesia Settings doctype not found")
        return False

    try:
        settings = frappe.get_single("Payroll Indonesia Settings")
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
        return True

    except Exception as e:
        logger.error(f"Error checking BPJS settings: {str(e)}")
        return False


def create_bpjs_summaries(date_obj=None):
    try:
        if not date_obj:
            today = getdate()
            date_obj = add_months(today, -1)

        first_day = get_first_day(date_obj)
        last_day = get_last_day(first_day)
        companies = frappe.get_all("Company", pluck="name")

        for company in companies:
            existing = frappe.db.exists(
                "BPJS Payment Summary",
                {"company": company, "start_date": first_day, "end_date": last_day},
            )

            if not existing:
                try:
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
    try:
        mapping = frappe.new_doc("BPJS Account Mapping")
        mapping.company = company
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


def validate_tax_cache(employee: Optional[str] = None) -> Dict[str, Any]:
    logger = frappe.logger("payroll_indonesia.cache")
    logger.info("Starting tax cache validation")
    
    result = {
        "status": "success",
        "validated": 0,
        "rebuilt": 0,
        "skipped": 0,
        "errors": 0,
        "message": ""
    }
    
    try:
        _ensure_tax_summary_fields()
        
        filters = {}
        if employee:
            filters["employee"] = employee
        else:
            yesterday = add_days(getdate(), -1)
            filters["modified"] = [">=", yesterday]
        
        tax_summaries = frappe.get_all(
            "Employee Tax Summary",
            filters=filters,
            fields=["name", "employee", "year"],
            limit=100 if not employee else None
        )
        
        if not tax_summaries and not employee:
            tax_summaries = frappe.get_all(
                "Employee Tax Summary",
                fields=["name", "employee", "year"],
                limit=50
            )
        
        rebuild_count = 0
        valid_count = 0
        error_count = 0
        
        for summary in tax_summaries:
            try:
                result["validated"] += 1
                if validate_summary_consistency(summary.name, summary.employee, summary.year):
                    valid_count += 1
                    continue
                
                rebuild_count += 1
                logger.warning(f"Tax summary {summary.name} inconsistent, rebuilding...")
                rebuild_tax_summary(summary.name)
                
                if rebuild_count >= 10 and not employee:
                    logger.info("Reached rebuild limit, will continue in next run")
                    result["skipped"] = len(tax_summaries) - result["validated"]
                    break
            except Exception as e:
                error_count += 1
                logger.error(f"Error validating summary {summary.name}: {str(e)}")
                continue
        
        cache_patterns = ["tax_summary:*", "ytd:*", "salary_slip:tax:*"]
        cleared_keys = 0
        for pattern in cache_patterns:
            cleared = cache_utils.clear_pattern(pattern)
            cleared_keys += cleared or 0
        
        result["rebuilt"] = rebuild_count
        result["errors"] = error_count
        result["message"] = (
            f"Validation complete: {valid_count} valid, {rebuild_count} rebuilt, "
            f"{error_count} errors, {cleared_keys} cache keys cleared"
        )
        
        logger.info(result["message"])
        return result
        
    except Exception as e:
        error_msg = f"Error in tax cache validation: {str(e)}"
        logger.error(error_msg)
        frappe.log_error(error_msg)
        result["status"] = "error"
        result["message"] = error_msg
        return result


def _ensure_tax_summary_fields():
    logger = frappe.logger("payroll_indonesia.cache")
    
    if not frappe.db.has_column("Employee Tax Summary", "year"):
        logger.warning("Employee Tax Summary missing 'year' field, creating via Property Setter")
        
        try:
            year_property = frappe.new_doc("Property Setter")
            year_property.doctype_or_field = "DocField"
            year_property.doc_type = "Employee Tax Summary"
            year_property.field_name = "year"
            year_property.property = "fieldtype"
            year_property.value = "Int"
            year_property.property_type = "Int"
            year_property.insert(ignore_permissions=True)
            
            label_property = frappe.new_doc("Property Setter")
            label_property.doctype_or_field = "DocField"
            label_property.doc_type = "Employee Tax Summary"
            label_property.field_name = "year"
            label_property.property = "label"
            label_property.value = "Tax Year"
            label_property.property_type = "Data"
            label_property.insert(ignore_permissions=True)
            
            logger.info("Created 'year' field via Property Setter")
            
            if not frappe.db.has_column("Employee Tax Summary", "year"):
                custom_field = frappe.new_doc("Custom Field")
                custom_field.dt = "Employee Tax Summary"
                custom_field.label = "Tax Year"
                custom_field.fieldname = "year"
                custom_field.fieldtype = "Int"
                custom_field.insert_after = "employee_name"
                custom_field.insert(ignore_permissions=True)
                logger.info("Created 'year' field via Custom Field")
        except Exception as e:
            logger.error(f"Failed to create year field: {str(e)}")
            raise frappe.ValidationError(
                "Employee Tax Summary is missing the 'year' field. Please add it manually."
            )


def _run_validate_tax_cache_tests():
    import unittest
    from unittest.mock import patch
    
    class TestValidateTaxCache(unittest.TestCase):
        def setUp(self):
            self.employee = "EMP-00001"
        
        @patch("frappe.get_all")
        @patch("payroll_indonesia.scheduler.tasks.validate_summary_consistency")
        @patch("payroll_indonesia.scheduler.tasks.rebuild_tax_summary")
        def test_validate_tax_cache(self, mock_rebuild, mock_validate, mock_get_all):
            mock_get_all.return_value = [
                frappe._dict({"name": "TAX-001", "employee": self.employee, "year": 2023}),
                frappe._dict({"name": "TAX-002", "employee": self.employee, "year": 2022})
            ]
            
            mock_validate.side_effect = [True, False]
            
            result = validate_tax_cache(self.employee)
            
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["validated"], 2)
            self.assertEqual(result["rebuilt"], 1)
            self.assertEqual(mock_rebuild.call_count, 1)
            mock_rebuild.assert_called_with("TAX-002")
    
    if frappe.conf.get("developer_mode"):
        unittest.main()


if frappe.conf.get("developer_mode") and not frappe.utils.cint(frappe.conf.unit_test):
    _run_validate_tax_cache_tests()


def validate_summary_consistency(summary_name: str, employee: str, year: int) -> bool:
    try:
        monthly_details = frappe.get_all(
            "Employee Tax Monthly Detail",
            filters={"parent": summary_name},
            fields=["month", "total_taxable_income", "pph21"],
        )
        if not monthly_details:
            logger.debug(f"No monthly details found for {summary_name}")
            return False
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": employee,
                "docstatus": 1,
                "posting_date": ["between", [f"{year}-01-01", f"{year}-12-31"]],
            },
            fields=["month(posting_date) as month", "total_taxable_income", "pph21_amount"],
        )
        slip_map = {}
        for slip in salary_slips:
            month = slip.month
            if month not in slip_map:
                slip_map[month] = {"total_taxable_income": 0, "pph21_amount": 0}
            slip_map[month]["total_taxable_income"] += slip.total_taxable_income or 0
            slip_map[month]["pph21_amount"] += slip.pph21_amount or 0
        for detail in monthly_details:
            month = detail.month
            if month not in slip_map:
                return False
            if (
                abs(detail.total_taxable_income - slip_map[month]["total_taxable_income"]) > 1
                or abs(detail.pph21 - slip_map[month]["pph21_amount"]) > 1
            ):
                return False
        return True
    except Exception as e:
        logger.error(f"Error validating summary consistency for {summary_name}: {str(e)}")
        return False


def rebuild_tax_summary(summary_name: str) -> None:
    try:
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
        summary.monthly_details = []
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": summary.employee,
                "docstatus": 1,
                "posting_date": ["between", [f"{summary.year}-01-01", f"{summary.year}-12-31"]],
            },
            fields=["name", "posting_date", "total_taxable_income", "pph21_amount"],
        )
        month_data = {}
        for slip in salary_slips:
            month = slip.posting_date.month
            if month not in month_data:
                month_data[month] = {"total_taxable_income": 0, "pph21": 0}
            month_data[month]["total_taxable_income"] += slip.total_taxable_income or 0
            month_data[month]["pph21"] += slip.pph21_amount or 0
        for month, data in month_data.items():
            summary.append(
                "monthly_details",
                {
                    "month": month,
                    "total_taxable_income": data["total_taxable_income"],
                    "pph21": data["pph21"],
                },
            )
        summary.total_taxable_income = sum(d["total_taxable_income"] for d in month_data.values())
        summary.total_tax = sum(d["pph21"] for d in month_data.values())
        summary.save()
        logger.info(f"Successfully rebuilt tax summary {summary_name}")
        cache_utils.clear_key(f"tax_summary:{summary.employee}:{summary.year}")

    except Exception as e:
        logger.error(f"Error rebuilding tax summary {summary_name}: {str(e)}")


def clear_caches():
    try:
        cache_utils.clear_all_caches()
        logger.info("All payroll caches cleared successfully")
    except Exception as e:
        logger.warning(f"Error clearing all caches: {str(e)}")


def cleanup_logs(days: int = 90) -> None:
    """Delete old Payroll Log entries.

    Args:
        days: Number of days to retain logs. Entries older than this
            threshold will be removed.
    """
    try:
        cutoff_date = add_days(getdate(), -days)
        count = frappe.db.count("Payroll Log", {"log_time": ["<", cutoff_date]})
        if count:
            frappe.db.delete(
                "Payroll Log",
                {"log_time": ["<", cutoff_date]},
            )
        logger.info(f"Deleted {count} Payroll Log entries older than {days} days")
    except Exception as e:
        logger.warning(f"Error cleaning Payroll Log: {str(e)}")

