# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-23 03:57:11 by dannyaudian

import frappe
import json
import re
from frappe import _
from frappe.utils import getdate, cint, flt, strip_html

#
# EMPLOYEE API ENDPOINTS
#


@frappe.whitelist(allow_guest=False)
def get_employee(name=None, filters=None):
    """API to get employee data"""
    if not frappe.has_permission("Employee", "read"):
        frappe.throw(_("Not permitted to read Employee data"), frappe.PermissionError)

    try:
        if name:
            # Get specific employee
            doc = frappe.get_doc("Employee", name)

            # Add tax and BPJS info
            doc.custom_data = {
                "tax_info": {
                    "npwp": doc.npwp if hasattr(doc, "npwp") else "",
                    "ktp": doc.ktp if hasattr(doc, "ktp") else "",
                    "status_pajak": doc.status_pajak if hasattr(doc, "status_pajak") else "TK0",
                }
            }

            # Get bank account info for salary payments
            doc.custom_data["bank_accounts"] = frappe.get_all(
                "Bank Account",
                filters={"party_type": "Employee", "party": name},
                fields=["name", "bank", "bank_account_no", "account_name", "is_default"],
            )

            return doc

        # Handle filters
        filters = json.loads(filters) if isinstance(filters, str) else (filters or {})

        # Get all employees matching filters
        employees = frappe.get_all(
            "Employee",
            filters=filters,
            fields=[
                "name",
                "employee_name",
                "company",
                "status",
                "date_of_joining",
                "department",
                "designation",
                "npwp",
                "ktp",
                "status_pajak",
            ],
        )

        # Return the employee list
        return {"data": employees, "count": len(employees)}
    except Exception as e:
        frappe.log_error(f"Error in get_employee: {str(e)}\n{frappe.get_traceback()}", "API Error")
        frappe.throw(_("Error retrieving Employee data: {0}").format(str(e)))


#
# SALARY SLIP API ENDPOINTS
#


@frappe.whitelist(allow_guest=False)
def get_salary_slips_by_employee(employee, year=None):
    """API to get all salary slips for a specific employee"""
    if not frappe.has_permission("Salary Slip", "read"):
        frappe.throw(_("Not permitted to read Salary Slip data"), frappe.PermissionError)

    try:
        # Build filters
        filters = {"employee": employee, "docstatus": 1}  # Only get submitted salary slips

        # Add year filter if provided
        if year:
            year = cint(year)
            filters.update(
                {"start_date": [">=", f"{year}-01-01"], "end_date": ["<=", f"{year}-12-31"]}
            )

        # Get all salary slips for this employee
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters=filters,
            fields=[
                "name",
                "employee",
                "employee_name",
                "start_date",
                "end_date",
                "gross_pay",
                "net_pay",
                "total_deduction",
                "posting_date",
                "company",
                "month",
                "is_using_ter",
                "ter_rate",
                "total_working_days",
                "total_bpjs",
                "npwp",
                "ktp",
            ],
            order_by="posting_date DESC",
        )

        # Group salary slips by year and month
        results = {}

        for slip in salary_slips:
            # Add formatted currency values
            slip["formatted_gross_pay"] = frappe.format(
                slip["gross_pay"], {"fieldtype": "Currency"}
            )
            slip["formatted_net_pay"] = frappe.format(slip["net_pay"], {"fieldtype": "Currency"})
            slip["formatted_total_deduction"] = frappe.format(
                slip["total_deduction"], {"fieldtype": "Currency"}
            )

            # Get period info
            slip_year = getdate(slip["end_date"]).year
            slip_month = getdate(slip["end_date"]).month

            # Add month name
            month_names = [
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            ]
            slip["month_name"] = (
                month_names[slip_month - 1] if 1 <= slip_month <= 12 else f"Month {slip_month}"
            )

            # Initialize year in results if not exists
            if slip_year not in results:
                results[slip_year] = {
                    "year": slip_year,
                    "slips_count": 0,
                    "total_gross": 0,
                    "total_net": 0,
                    "months": {},
                }

            # Initialize month in year if not exists
            if slip_month not in results[slip_year]["months"]:
                results[slip_year]["months"][slip_month] = {
                    "month": slip_month,
                    "month_name": slip["month_name"],
                    "slips": [],
                }

            # Add slip to month
            results[slip_year]["months"][slip_month]["slips"].append(slip)

            # Update year totals
            results[slip_year]["slips_count"] += 1
            results[slip_year]["total_gross"] += flt(slip["gross_pay"])
            results[slip_year]["total_net"] += flt(slip["net_pay"])

        # Add formatted totals to years
        for y in results:
            results[y]["formatted_total_gross"] = frappe.format(
                results[y]["total_gross"], {"fieldtype": "Currency"}
            )
            results[y]["formatted_total_net"] = frappe.format(
                results[y]["total_net"], {"fieldtype": "Currency"}
            )

            # Convert months dict to sorted list
            months_list = []
            for m in sorted(results[y]["months"].keys()):
                months_list.append(results[y]["months"][m])
            results[y]["months"] = months_list

        # Convert years dict to list and sort by year descending
        years_list = []
        for y in sorted(results.keys(), reverse=True):
            years_list.append(results[y])

        return {
            "status": "success",
            "employee": employee,
            "employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
            "total_slips": sum(y["slips_count"] for y in years_list),
            "data": years_list,
        }
    except Exception as e:
        frappe.log_error(
            f"Error getting salary slips for {employee}: {str(e)}\n{frappe.get_traceback()}",
            "API Error",
        )
        frappe.throw(_("Error retrieving salary slips: {0}").format(str(e)))


@frappe.whitelist(allow_guest=False)
def get_salary_slip(name):
    """API to get a specific salary slip with details"""
    if not frappe.has_permission("Salary Slip", "read"):
        frappe.throw(_("Not permitted to read Salary Slip data"), frappe.PermissionError)

    try:
        # Get the salary slip document
        doc = frappe.get_doc("Salary Slip", name)

        # Format currency values
        result = {
            "salary_slip": name,
            "employee": doc.employee,
            "employee_name": doc.employee_name,
            "start_date": doc.start_date,
            "end_date": doc.end_date,
            "posting_date": doc.posting_date,
            "gross_pay": doc.gross_pay,
            "net_pay": doc.net_pay,
            "total_deduction": doc.total_deduction,
            "formatted_gross_pay": frappe.format(doc.gross_pay, {"fieldtype": "Currency"}),
            "formatted_net_pay": frappe.format(doc.net_pay, {"fieldtype": "Currency"}),
            "formatted_total_deduction": frappe.format(
                doc.total_deduction, {"fieldtype": "Currency"}
            ),
            "company": doc.company,
            "docstatus": doc.docstatus,
            "period": f"{frappe.format(doc.start_date, {'fieldtype': 'Date'})} to {frappe.format(doc.end_date, {'fieldtype': 'Date'})}",
        }

        # Add tax information
        result["tax_info"] = {
            "npwp": doc.npwp if hasattr(doc, "npwp") else "",
            "ktp": doc.ktp if hasattr(doc, "ktp") else "",
            "is_using_ter": doc.is_using_ter if hasattr(doc, "is_using_ter") else 0,
            "ter_rate": doc.ter_rate if hasattr(doc, "ter_rate") else 0,
        }

        # Add earnings details
        earnings = []
        for earning in doc.earnings:
            earnings.append(
                {
                    "salary_component": earning.salary_component,
                    "amount": earning.amount,
                    "formatted_amount": frappe.format(earning.amount, {"fieldtype": "Currency"}),
                }
            )
        result["earnings"] = earnings

        # Add deductions details
        deductions = []
        for deduction in doc.deductions:
            deductions.append(
                {
                    "salary_component": deduction.salary_component,
                    "amount": deduction.amount,
                    "formatted_amount": frappe.format(deduction.amount, {"fieldtype": "Currency"}),
                }
            )
        result["deductions"] = deductions

        # Get employee additional info
        result["employee_details"] = {
            "department": frappe.db.get_value("Employee", doc.employee, "department"),
            "designation": frappe.db.get_value("Employee", doc.employee, "designation"),
            "employment_type": frappe.db.get_value("Employee", doc.employee, "employment_type"),
            "bank_account": get_employee_bank_account(doc.employee),
        }

        return result
    except Exception as e:
        frappe.log_error(
            f"Error getting salary slip {name}: {str(e)}\n{frappe.get_traceback()}", "API Error"
        )
        frappe.throw(_("Error retrieving salary slip: {0}").format(str(e)))


def get_employee_bank_account(employee):
    """Get employee default bank account"""
    bank_account = None

    try:
        # First try to get default bank account
        bank_accounts = frappe.get_all(
            "Bank Account",
            filters={"party_type": "Employee", "party": employee, "is_default": 1},
            fields=["name", "bank", "bank_account_no", "account_name"],
        )

        if bank_accounts:
            bank_account = bank_accounts[0]
        else:
            # If no default found, get any bank account
            bank_accounts = frappe.get_all(
                "Bank Account",
                filters={"party_type": "Employee", "party": employee},
                fields=["name", "bank", "bank_account_no", "account_name"],
            )

            if bank_accounts:
                bank_account = bank_accounts[0]
    except Exception:
        pass

    return bank_account


@frappe.whitelist(allow_guest=False)
def get_recent_salary_slips(limit=10, company=None):
    """API to get recent salary slips across the company"""
    if not frappe.has_permission("Salary Slip", "read"):
        frappe.throw(_("Not permitted to read Salary Slip data"), frappe.PermissionError)

    try:
        # Build filters
        filters = {"docstatus": 1}  # Only get submitted salary slips

        # Add company filter if provided
        if company:
            filters["company"] = company

        # Get recent salary slips
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters=filters,
            fields=[
                "name",
                "employee",
                "employee_name",
                "start_date",
                "end_date",
                "posting_date",
                "gross_pay",
                "net_pay",
                "company",
            ],
            order_by="posting_date DESC, creation DESC",
            limit_page_length=cint(limit),
        )

        # Enhance each slip with formatted data
        for slip in salary_slips:
            slip["formatted_gross_pay"] = frappe.format(
                slip["gross_pay"], {"fieldtype": "Currency"}
            )
            slip["formatted_net_pay"] = frappe.format(slip["net_pay"], {"fieldtype": "Currency"})
            slip["period"] = (
                f"{frappe.format(slip['start_date'], {'fieldtype': 'Date'})} to {frappe.format(slip['end_date'], {'fieldtype': 'Date'})}"
            )

            # Add department and designation
            slip["department"] = frappe.db.get_value("Employee", slip["employee"], "department")
            slip["designation"] = frappe.db.get_value("Employee", slip["employee"], "designation")

        return {"status": "success", "count": len(salary_slips), "data": salary_slips}
    except Exception as e:
        frappe.log_error(
            f"Error getting recent salary slips: {str(e)}\n{frappe.get_traceback()}", "API Error"
        )
        frappe.throw(_("Error retrieving recent salary slips: {0}").format(str(e)))


@frappe.whitelist()
def diagnose_salary_slip(slip_name):
    """
    Diagnose issues with salary slip calculation
    Args:
        slip_name: Name of the salary slip
    Returns:
        dict: Detailed diagnostic information
    """
    try:
        # Get the document
        doc = frappe.get_doc("Salary Slip", slip_name)

        # Collect key information for debugging
        result = {
            "name": doc.name,
            "employee": doc.employee,
            "employee_name": doc.employee_name,
            "start_date": doc.start_date,
            "end_date": doc.end_date,
            "posting_date": doc.posting_date,
            "gross_pay": doc.gross_pay,
            "total_deduction": doc.total_deduction,
            "net_pay": doc.net_pay,
            "earnings": [],
            "deductions": [],
            "tax_details": {},
        }

        # Get earnings details
        for earning in doc.earnings:
            result["earnings"].append(
                {"component": earning.salary_component, "amount": earning.amount}
            )

        # Get deductions details
        for deduction in doc.deductions:
            result["deductions"].append(
                {"component": deduction.salary_component, "amount": deduction.amount}
            )

        # Check for tax calculation method and TER info
        result["tax_details"]["is_using_ter"] = getattr(doc, "is_using_ter", 0)
        result["tax_details"]["ter_rate"] = getattr(doc, "ter_rate", 0)

        # Check for tax amounts
        pph21_amount = 0
        for deduction in doc.deductions:
            if deduction.salary_component == "PPh 21" or "PPh 21" in deduction.salary_component:
                pph21_amount = deduction.amount
                break

        result["tax_details"]["pph21_amount"] = pph21_amount

        # Extract tax calculation details from payroll_note
        if hasattr(doc, "payroll_note") and doc.payroll_note:
            result["payroll_note"] = doc.payroll_note

            # Try to extract key information from payroll_note
            note = strip_html(doc.payroll_note)

            # Extract tax method
            if "Method: TER" in note:
                result["tax_details"]["method"] = "TER"
            elif "Method: PROGRESSIVE" in note:
                result["tax_details"]["method"] = "PROGRESSIVE"

            # Extract gross pay from note
            gross_pattern = r"Penghasilan Bruto: Rp ([\d,]+)"
            gross_match = re.search(gross_pattern, note)
            if gross_match:
                result["tax_details"]["note_gross_pay"] = gross_match.group(1)

            # Extract TER rate if present
            ter_pattern = r"Tarif Efektif Rata-rata: ([\d.]+)%"
            ter_match = re.search(ter_pattern, note)
            if ter_match:
                result["tax_details"]["note_ter_rate"] = ter_match.group(1)

        # Check if any TER adjustment was made
        if "gross_pay adjusted" in str(result.get("payroll_note", "")):
            result["tax_details"]["gross_pay_adjusted"] = True

            # Try to extract before and after values
            adjustment_pattern = r"gross_pay adjusted from ([\d,]+) to ([\d,]+)"
            adjustment_match = re.search(
                adjustment_pattern, str(result.get("payroll_note", "")), re.IGNORECASE
            )
            if adjustment_match:
                result["tax_details"]["adjusted_from"] = adjustment_match.group(1)
                result["tax_details"]["adjusted_to"] = adjustment_match.group(2)

        # Check additional tax-related fields if they exist
        for field in ["biaya_jabatan", "netto", "total_bpjs", "ptkp"]:
            if hasattr(doc, field):
                result["tax_details"][field] = getattr(doc, field)

        return result
    except Exception as e:
        return {"error": str(e), "traceback": frappe.get_traceback()}


#
# TAX SUMMARY API ENDPOINTS
#


@frappe.whitelist(allow_guest=False)
def refresh_tax_summary(employee=None, year=None, salary_slip=None, force=False):
    """
    Manually refresh the Employee Tax Summary for a specific employee, year, or salary slip.
    This is a high-level API for the UI to trigger a refresh operation.

    Args:
        employee: The employee code to refresh (required unless salary_slip is provided)
        year: The tax year to refresh (defaults to current year if not provided)
        salary_slip: Specific salary slip to refresh tax summary for
        force: Whether to force recreation of the tax summary (default: False)

    Returns:
        dict: Status and result of the operation
    """
    # Check permissions
    if not frappe.has_permission("Employee Tax Summary", "write"):
        frappe.throw(_("Not permitted to update Tax Summary data"), frappe.PermissionError)

    try:
        # Case 1: Refresh specific salary slip
        if salary_slip:
            from payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary import (
                create_from_salary_slip,
            )

            # Get the salary slip to access its fields
            slip = frappe.get_doc("Salary Slip", salary_slip)
            if slip.docstatus != 1:
                return {
                    "status": "error",
                    "message": _("Salary slip must be submitted to update tax summary"),
                }

            # Queue the update
            result = create_from_salary_slip(salary_slip)

            if result:
                return {
                    "status": "success",
                    "message": _("Tax summary updated from salary slip {0}").format(salary_slip),
                    "tax_summary": result,
                }
            else:
                return {
                    "status": "error",
                    "message": _("Failed to update tax summary from salary slip {0}").format(
                        salary_slip
                    ),
                }

        # Case 2: Refresh employee+year combination
        elif employee:
            # Set default year if not provided
            if not year:
                year = getdate().year

            try:
                # Verify employee exists
                if not frappe.db.exists("Employee", employee):
                    return {
                        "status": "error",
                        "message": _("Employee {0} not found").format(employee),
                    }

                # Queue the refresh job in background
                from payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary import (
                    refresh_tax_summary as _refresh_func,
                )

                job_name = f"refresh_tax_summary_{employee}_{year}"

                # Use enqueue to run in background for better performance
                frappe.enqueue(
                    _refresh_func,
                    queue="long",
                    timeout=1200,  # 20 minutes timeout for large datasets
                    employee=employee,
                    year=year,
                    force=force,
                    job_name=job_name,
                    now=False,  # Run in background
                )

                return {
                    "status": "queued",
                    "message": _("Tax summary refresh queued in background job: {0}").format(
                        job_name
                    ),
                    "employee": employee,
                    "year": year,
                }

            except Exception as e:
                frappe.log_error(
                    f"Error queuing tax summary refresh for {employee}, {year}: {str(e)}\n{frappe.get_traceback()}",
                    "Tax Summary API Error",
                )

                return {
                    "status": "error",
                    "message": _("Error refreshing tax summary: {0}").format(str(e)),
                    "details": str(e),
                }
        else:
            return {
                "status": "error",
                "message": _("Either employee or salary_slip must be provided"),
            }

    except Exception as e:
        frappe.log_error(
            f"Error in refresh_tax_summary API: {str(e)}\n{frappe.get_traceback()}",
            "Tax Summary API Error",
        )

        return {
            "status": "error",
            "message": _("Error refreshing tax summary: {0}").format(str(e)),
            "details": frappe.get_traceback(),
        }


@frappe.whitelist(allow_guest=False)
def get_tax_summary_status(employee, year=None):
    """
    Get the status of tax summaries for an employee

    Args:
        employee: Employee code
        year: Optional tax year (defaults to current year)

    Returns:
        dict: Tax summary status data
    """
    if not frappe.has_permission("Employee Tax Summary", "read"):
        frappe.throw(_("Not permitted to view Tax Summary data"), frappe.PermissionError)

    try:
        # Default to current year if not specified
        if not year:
            year = getdate().year
        else:
            year = cint(year)

        # Check if tax summary exists
        tax_summary = frappe.db.get_value(
            "Employee Tax Summary",
            {"employee": employee, "year": year},
            ["name", "ytd_tax", "is_using_ter", "ter_rate"],
            as_dict=True,
        )

        # Get all salary slips for this employee and year
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": employee,
                "docstatus": 1,
                "start_date": [">=", f"{year}-01-01"],
                "end_date": ["<=", f"{year}-12-31"],
            },
            fields=["name", "start_date", "end_date", "posting_date", "docstatus"],
            order_by="start_date ASC",
        )

        result = {
            "employee": employee,
            "year": year,
            "tax_summary_exists": bool(tax_summary),
            "slip_count": len(salary_slips),
            "months_covered": [],
        }

        # Add tax summary details if it exists
        if tax_summary:
            result["tax_summary"] = {
                "name": tax_summary.name,
                "ytd_tax": tax_summary.ytd_tax,
                "is_using_ter": tax_summary.is_using_ter,
                "ter_rate": tax_summary.ter_rate,
                "formatted_ytd_tax": frappe.format(tax_summary.ytd_tax, {"fieldtype": "Currency"}),
            }

            # Get monthly data
            monthly_data = frappe.get_all(
                "Employee Monthly Tax Detail",
                filters={"parent": tax_summary.name},
                fields=[
                    "month",
                    "gross_pay",
                    "tax_amount",
                    "is_using_ter",
                    "ter_rate",
                    "salary_slip",
                ],
                order_by="month ASC",
            )

            # Process monthly data
            result["monthly_data"] = []
            for month in range(1, 13):
                month_data = next((m for m in monthly_data if m.month == month), None)

                month_status = {
                    "month": month,
                    "month_name": [
                        "Jan",
                        "Feb",
                        "Mar",
                        "Apr",
                        "May",
                        "Jun",
                        "Jul",
                        "Aug",
                        "Sep",
                        "Oct",
                        "Nov",
                        "Dec",
                    ][month - 1],
                    "has_data": bool(month_data and month_data.gross_pay > 0),
                    "has_slip": any(getdate(s.start_date).month == month for s in salary_slips),
                }

                if month_data and month_data.gross_pay > 0:
                    month_status["data"] = {
                        "gross_pay": month_data.gross_pay,
                        "tax_amount": month_data.tax_amount,
                        "is_using_ter": month_data.is_using_ter,
                        "ter_rate": month_data.ter_rate,
                        "salary_slip": month_data.salary_slip,
                        "formatted_gross": frappe.format(
                            month_data.gross_pay, {"fieldtype": "Currency"}
                        ),
                        "formatted_tax": frappe.format(
                            month_data.tax_amount, {"fieldtype": "Currency"}
                        ),
                    }

                    # Add to months covered
                    if month_status["has_data"]:
                        result["months_covered"].append(month)

                result["monthly_data"].append(month_status)

        # Include summary statistics
        result["stats"] = {
            "months_with_data": len(result.get("months_covered", [])),
            "potential_months": len(set(getdate(s.start_date).month for s in salary_slips)),
            "missing_months": [],
        }

        # Check for months with slips but no tax data
        for slip in salary_slips:
            slip_month = getdate(slip.start_date).month
            if slip_month not in result.get("months_covered", []):
                result["stats"]["missing_months"].append(
                    {
                        "month": slip_month,
                        "month_name": [
                            "Jan",
                            "Feb",
                            "Mar",
                            "Apr",
                            "May",
                            "Jun",
                            "Jul",
                            "Aug",
                            "Sep",
                            "Oct",
                            "Nov",
                            "Dec",
                        ][slip_month - 1],
                        "salary_slip": slip.name,
                    }
                )

        # Add refresh recommendation if needed
        if result["stats"]["missing_months"]:
            result["needs_refresh"] = True
            result["refresh_recommendation"] = _(
                "Tax summary is missing data for {0} months with salary slips. Consider refreshing the tax summary."
            ).format(len(result["stats"]["missing_months"]))
        else:
            result["needs_refresh"] = False

        return result

    except Exception as e:
        frappe.log_error(
            f"Error getting tax summary status for {employee}, {year}: {str(e)}\n{frappe.get_traceback()}",
            "Tax Summary API Error",
        )

        return {
            "status": "error",
            "message": _("Error retrieving tax summary status: {0}").format(str(e)),
        }


@frappe.whitelist(allow_guest=False)
def bulk_refresh_tax_summaries(employees=None, year=None, company=None):
    """
    Start a bulk refresh operation for multiple employees' tax summaries

    Args:
        employees: List of employee codes (optional)
        year: Tax year to refresh (defaults to current year)
        company: Company to refresh all employees for (optional)

    Returns:
        dict: Job information
    """
    if not frappe.has_permission("Employee Tax Summary", "write"):
        frappe.throw(_("Not permitted to update Tax Summary data"), frappe.PermissionError)

    try:
        # Set default year
        if not year:
            year = getdate().year
        else:
            year = cint(year)

        # Handle JSON string
        if isinstance(employees, str):
            try:
                employees = json.loads(employees)
            except ValueError:
                # If single value, convert to list
                employees = [employees]

        # If no employees specified but company is, get all active employees for company
        if not employees and company:
            employees = [
                e.name
                for e in frappe.get_all(
                    "Employee", filters={"company": company, "status": "Active"}, fields=["name"]
                )
            ]

        if not employees:
            return {"status": "error", "message": _("No employees specified for bulk refresh")}

        # Queue the bulk operation
        job_name = f"bulk_tax_refresh_{getdate().strftime('%Y%m%d%H%M%S')}"

        frappe.enqueue(
            "payroll_indonesia.override.salary_slip.refresh_multiple_tax_summaries",
            queue="long",
            timeout=3600,  # 1 hour timeout
            employees=employees,
            year=year,
            job_name=job_name,
            now=False,  # Run in background
            is_async=True,
        )

        return {
            "status": "queued",
            "message": _("Bulk tax summary refresh queued as job: {0}").format(job_name),
            "job": job_name,
            "employee_count": len(employees),
            "year": year,
        }

    except Exception as e:
        frappe.log_error(
            f"Error in bulk_refresh_tax_summaries: {str(e)}\n{frappe.get_traceback()}",
            "Tax Summary API Error",
        )

        return {"status": "error", "message": _("Error starting bulk refresh: {0}").format(str(e))}


# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 00:12:13 by dannyaudian

import frappe
from frappe import _
from frappe.utils import flt

from payroll_indonesia.config import get_live_config
from payroll_indonesia.frappe_helpers import safe_execute

@frappe.whitelist()
@safe_execute(default_value={}, log_exception=True)
def get_bpjs_limits():
    """
    Get BPJS validation limits from configuration.
    
    Returns:
        dict: Validation rules for BPJS settings
    """
    # Get validation rules from config
    config = get_live_config()
    bpjs_config = config.get("bpjs", {})
    validation_rules = bpjs_config.get("validation_rules", {})
    
    # If no rules defined, provide defaults
    if not validation_rules or not validation_rules.get("percentage_ranges"):
        validation_rules = {
            "percentage_ranges": [
                {
                    "field": "kesehatan_employee_percent",
                    "min": 0,
                    "max": 5,
                    "error_msg": "BPJS Kesehatan employee percentage must be between 0% and 5%"
                },
                {
                    "field": "kesehatan_employer_percent",
                    "min": 0,
                    "max": 10,
                    "error_msg": "BPJS Kesehatan employer percentage must be between 0% and 10%"
                },
                {
                    "field": "jht_employee_percent",
                    "min": 0,
                    "max": 5,
                    "error_msg": "JHT employee percentage must be between 0% and 5%"
                },
                {
                    "field": "jht_employer_percent",
                    "min": 0,
                    "max": 10,
                    "error_msg": "JHT employer percentage must be between 0% and 10%"
                },
                {
                    "field": "jp_employee_percent",
                    "min": 0,
                    "max": 5,
                    "error_msg": "JP employee percentage must be between 0% and 5%"
                },
                {
                    "field": "jp_employer_percent",
                    "min": 0,
                    "max": 5,
                    "error_msg": "JP employer percentage must be between 0% and 5%"
                },
                {
                    "field": "jkk_percent",
                    "min": 0,
                    "max": 5,
                    "error_msg": "JKK percentage must be between 0% and 5%"
                },
                {
                    "field": "jkm_percent",
                    "min": 0,
                    "max": 5,
                    "error_msg": "JKM percentage must be between 0% and 5%"
                }
            ]
        }
    
    return validation_rules
