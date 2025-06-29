# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 00:31:53 by dannyaudian

"""
Payroll Indonesia API endpoints.

Provides a thin API layer for accessing payroll functionality:
- Employee data
- Salary slip information
- Tax summary operations
- BPJS calculation
"""

import json
import logging
from typing import Dict, Any, List, Optional, Union

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from payroll_indonesia.config import get_live_config
from payroll_indonesia.frappe_helpers import safe_execute
from payroll_indonesia.payroll_indonesia.utils import (
    get_employee_details,
    hitung_bpjs,
    get_ytd_tax_info,
    get_ytd_totals
)

# Configure logger
logger = logging.getLogger('payroll_api')


@frappe.whitelist(allow_guest=False)
@safe_execute(log_exception=True)
def get_employee(name: str = None, filters: str = None) -> Dict[str, Any]:
    """
    API to get employee data.
    
    Args:
        name: Employee ID
        filters: JSON string of filters
        
    Returns:
        dict: Employee data or list
    """
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
            "date_of_joining", "department", "designation"
        ]
    )
    
    return {
        "status": "success",
        "count": len(employees),
        "data": employees
    }


@frappe.whitelist(allow_guest=False)
@safe_execute(log_exception=True)
def get_employee_tax_info(employee: str) -> Dict[str, Any]:
    """
    Get employee tax and BPJS information.
    
    Args:
        employee: Employee ID
        
    Returns:
        dict: Tax and BPJS information
    """
    if not frappe.has_permission("Employee", "read"):
        frappe.throw(_("Not permitted to read Employee data"), 
                     frappe.PermissionError)
    
    employee_doc = get_employee_details(employee)
    if not employee_doc:
        frappe.throw(_("Employee not found"))
    
    # Get current date
    today = getdate()
    
    # Get YTD tax info
    ytd_info = get_ytd_tax_info(employee, today)
    
    return {
        "status": "success",
        "data": {
            "name": employee_doc.get("name"),
            "employee_name": employee_doc.get("employee_name"),
            "tax_status": employee_doc.get("status_pajak", "TK0"),
            "npwp": employee_doc.get("npwp", ""),
            "ktp": employee_doc.get("ktp", ""),
            "ytd_tax": ytd_info.get("ytd_tax", 0),
            "bpjs_kesehatan": employee_doc.get("ikut_bpjs_kesehatan", 1),
            "bpjs_ketenagakerjaan": employee_doc.get(
                "ikut_bpjs_ketenagakerjaan", 1)
        }
    }


@frappe.whitelist(allow_guest=False)
@safe_execute(log_exception=True)
def get_salary_slip(name: str) -> Dict[str, Any]:
    """
    API to get a specific salary slip with details.
    
    Args:
        name: Salary slip name
        
    Returns:
        dict: Salary slip details
    """
    if not frappe.has_permission("Salary Slip", "read"):
        frappe.throw(_("Not permitted to read Salary Slip data"), 
                     frappe.PermissionError)
    
    # Get salary slip document
    doc = frappe.get_doc("Salary Slip", name)
    
    # Prepare basic information
    result = {
        "name": doc.name,
        "employee": doc.employee,
        "employee_name": doc.employee_name,
        "company": doc.company,
        "start_date": doc.start_date,
        "end_date": doc.end_date,
        "posting_date": doc.posting_date,
        "gross_pay": doc.gross_pay,
        "net_pay": doc.net_pay,
        "total_deduction": doc.total_deduction,
        "docstatus": doc.docstatus,
        "earnings": [
            {"component": e.salary_component, "amount": e.amount}
            for e in doc.earnings
        ],
        "deductions": [
            {"component": d.salary_component, "amount": d.amount}
            for d in doc.deductions
        ]
    }
    
    # Add tax details if available
    if hasattr(doc, "is_using_ter"):
        result["tax_info"] = {
            "is_using_ter": doc.is_using_ter,
            "ter_rate": getattr(doc, "ter_rate", 0),
            "npwp": getattr(doc, "npwp", ""),
            "ktp": getattr(doc, "ktp", "")
        }
    
    return {
        "status": "success",
        "data": result
    }


@frappe.whitelist(allow_guest=False)
@safe_execute(log_exception=True)
def get_salary_slips_by_employee(employee: str, 
                                year: int = None) -> Dict[str, Any]:
    """
    Get salary slips for a specific employee.
    
    Args:
        employee: Employee ID
        year: Filter by year (optional)
        
    Returns:
        dict: Salary slips grouped by year and month
    """
    if not frappe.has_permission("Salary Slip", "read"):
        frappe.throw(_("Not permitted to read Salary Slip data"), 
                     frappe.PermissionError)
    
    # Build filters
    filters = {"employee": employee, "docstatus": 1}
    
    # Add year filter if provided
    if year:
        year = cint(year)
        filters.update({
            "start_date": [">=", f"{year}-01-01"],
            "end_date": ["<=", f"{year}-12-31"]
        })
    
    # Get salary slips
    salary_slips = frappe.get_all(
        "Salary Slip",
        filters=filters,
        fields=[
            "name", "employee", "employee_name", "start_date", "end_date",
            "posting_date", "gross_pay", "net_pay", "total_deduction",
            "company", "month"
        ],
        order_by="posting_date DESC"
    )
    
    return {
        "status": "success",
        "employee": employee,
        "employee_name": frappe.db.get_value("Employee", employee, 
                                            "employee_name"),
        "count": len(salary_slips),
        "data": salary_slips
    }


@frappe.whitelist(allow_guest=False)
@safe_execute(log_exception=True)
def hitung_bpjs_api(gaji_pokok: float) -> Dict[str, Any]:
    """
    Calculate BPJS contributions based on salary.
    
    Args:
        gaji_pokok: Base salary amount
        
    Returns:
        dict: BPJS contribution details
    """
    # Convert input to float
    gaji_pokok = flt(gaji_pokok)
    
    # Calculate BPJS using utility function
    hasil = hitung_bpjs(gaji_pokok)
    
    return {
        "status": "success",
        "data": hasil
    }


@frappe.whitelist(allow_guest=False)
@safe_execute(log_exception=True)
def get_tax_summary(employee: str, year: int = None) -> Dict[str, Any]:
    """
    Get tax summary for an employee.
    
    Args:
        employee: Employee ID
        year: Tax year (defaults to current year)
        
    Returns:
        dict: Tax summary information
    """
    if not frappe.has_permission("Employee", "read"):
        frappe.throw(_("Not permitted to read Employee data"), 
                     frappe.PermissionError)
    
    # Default to current year
    if not year:
        year = getdate().year
    else:
        year = cint(year)
    
    # Get YTD totals
    ytd_data = get_ytd_totals(employee, year, 12)
    
    # Check if tax summary exists
    tax_summary = frappe.db.get_value(
        "Employee Tax Summary",
        {"employee": employee, "year": year},
        ["name", "ytd_tax", "is_using_ter", "ter_rate"],
        as_dict=True
    )
    
    # Build response
    result = {
        "employee": employee,
        "employee_name": frappe.db.get_value("Employee", employee, 
                                            "employee_name"),
        "year": year,
        "ytd_gross": ytd_data.get("ytd_gross", 0),
        "ytd_tax": ytd_data.get("ytd_tax", 0),
        "ytd_bpjs": ytd_data.get("ytd_bpjs", 0),
        "ytd_netto": ytd_data.get("ytd_netto", 0),
        "is_using_ter": ytd_data.get("is_using_ter", False),
        "ter_rate": ytd_data.get("ter_rate", 0),
        "tax_summary_exists": bool(tax_summary)
    }
    
    # Add tax summary reference if it exists
    if tax_summary:
        result["tax_summary_name"] = tax_summary.name
    
    return {
        "status": "success",
        "data": result
    }


@frappe.whitelist(allow_guest=False)
@safe_execute(log_exception=True)
def refresh_tax_summary(employee: str, year: int = None) -> Dict[str, Any]:
    """
    Refresh tax summary for an employee.
    
    Args:
        employee: Employee ID
        year: Tax year (defaults to current year)
        
    Returns:
        dict: Job information
    """
    if not frappe.has_permission("Employee Tax Summary", "write"):
        frappe.throw(_("Not permitted to update Tax Summary data"), 
                     frappe.PermissionError)
    
    # Default to current year
    if not year:
        year = getdate().year
    else:
        year = cint(year)
    
    # Queue the refresh job
    job = frappe.enqueue(
        "payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary."
        "employee_tax_summary.refresh_tax_summary",
        employee=employee,
        year=year,
        force=True,
        queue="long",
        timeout=1200  # 20 minutes
    )
    
    return {
        "status": "success",
        "message": _("Tax summary refresh queued"),
        "job_id": job.id if job else None,
        "employee": employee,
        "year": year
    }


@frappe.whitelist(allow_guest=False)
@safe_execute(log_exception=True)
def get_bpjs_limits() -> Dict[str, Any]:
    """
    Get BPJS validation limits from configuration.
    
    Returns:
        dict: BPJS validation rules
    """
    # Get configuration
    config = get_live_config()
    bpjs_config = config.get('bpjs', {})
    
    # Get validation rules
    validation_rules = bpjs_config.get("validation_rules", {})
    
    # If no rules defined, use defaults
    if not validation_rules or not validation_rules.get("percentage_ranges"):
        # Get default limits from config
        percentage_ranges = []
        
        # Add kesehatan fields
        percentage_ranges.append({
            "field": "kesehatan_employee_percent",
            "min": 0,
            "max": 5,
            "error_msg": "BPJS Kesehatan employee percentage must be "
                         "between 0% and 5%"
        })
        percentage_ranges.append({
            "field": "kesehatan_employer_percent",
            "min": 0,
            "max": 10,
            "error_msg": "BPJS Kesehatan employer percentage must be "
                         "between 0% and 10%"
        })
        
        # Add JHT fields
        percentage_ranges.append({
            "field": "jht_employee_percent",
            "min": 0,
            "max": 5,
            "error_msg": "JHT employee percentage must be between 0% and 5%"
        })
        percentage_ranges.append({
            "field": "jht_employer_percent",
            "min": 0,
            "max": 10,
            "error_msg": "JHT employer percentage must be between 0% and 10%"
        })
        
        # Add JP fields
        percentage_ranges.append({
            "field": "jp_employee_percent",
            "min": 0,
            "max": 5,
            "error_msg": "JP employee percentage must be between 0% and 5%"
        })
        percentage_ranges.append({
            "field": "jp_employer_percent",
            "min": 0,
            "max": 5,
            "error_msg": "JP employer percentage must be between 0% and 5%"
        })
        
        # Add JKK and JKM fields
        percentage_ranges.append({
            "field": "jkk_percent",
            "min": 0,
            "max": 5,
            "error_msg": "JKK percentage must be between 0% and 5%"
        })
        percentage_ranges.append({
            "field": "jkm_percent",
            "min": 0,
            "max": 5,
            "error_msg": "JKM percentage must be between 0% and 5%"
        })
        
        validation_rules = {
            "percentage_ranges": percentage_ranges
        }
    
    return validation_rules
