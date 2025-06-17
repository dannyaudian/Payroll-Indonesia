# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-17 06:28:51 by dannyaudian

import frappe
from frappe import _
from frappe.utils import nowdate, flt
from datetime import datetime
from typing import Dict, Optional, Any

# Import constants
from payroll_indonesia.constants import CACHE_MEDIUM, CACHE_LONG, TER_CATEGORY_A, TER_CATEGORY_B

# Import from pph_ter directly rather than ter_calculator
from payroll_indonesia.payroll_indonesia.tax.pph_ter import map_ptkp_to_ter_category

# Import tax calculation logic from the centralized ter_logic module
from payroll_indonesia.payroll_indonesia.tax.ter_logic import hitung_pph_tahunan

# Import cache utilities
from payroll_indonesia.utilities.cache_utils import get_cached_value, cache_value

# Import shared YTD functions
from payroll_indonesia.payroll_indonesia.utils import get_employee_details


def prepare_tax_report(year: Optional[int] = None, company: Optional[str] = None) -> Dict[str, Any]:
    """
    Prepare annual tax reports for employees with PMK 168/2023 compliance

    This function should be called at the end of the tax year
    to prepare tax reports (form 1721-A1) for each employee

    Args:
        year: Tax year to process. Defaults to current year.
        company: Company to process. If not provided, all companies are processed.

    Returns:
        Summary of processed reports
    """
    try:
        # Validate parameters
        if not year:
            year = datetime.now().year
            frappe.msgprint(_("Tax year not specified, using current year: {0}").format(year))

        # Validate year is valid
        current_year = datetime.now().year
        if not isinstance(year, int) or year < 2000 or year > current_year + 1:
            frappe.throw(
                _("Invalid tax year: {0}. Must be between 2000 and {1}").format(
                    year, current_year + 1
                )
            )

        # Check if company exists if provided
        if company and not frappe.db.exists("Company", company):
            frappe.throw(_("Company {0} not found").format(company))

        # Prepare start and end dates for the year
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        # Statistics
        summary = {
            "year": year,
            "company": company or "All Companies",
            "total_employees": 0,
            "processed": 0,
            "errors": 0,
            "details": [],
        }

        # Get list of employees with salary slips in the specified period - using caching for efficiency
        cache_key = f"tax_report_employees:{year}:{company or 'all'}"
        employee_list = get_cached_value(cache_key)

        if employee_list is None:
            # Use parameterized query for better security and performance
            query = """
                SELECT DISTINCT employee, employee_name
                FROM `tabSalary Slip`
                WHERE posting_date BETWEEN %s AND %s
                AND docstatus = 1
            """
            params = [start_date, end_date]

            # Add company filter if provided
            if company:
                query += " AND company = %s"
                params.append(company)

            employee_list = frappe.db.sql(query, params, as_dict=1)

            # Cache result for efficiency
            cache_value(cache_key, employee_list or [], CACHE_MEDIUM)

        if not employee_list:
            frappe.msgprint(_("No employees found with salary slips in {0}").format(year))
            return summary

        summary["total_employees"] = len(employee_list)

        # Process each employee - optionally do this in chunks for large datasets
        for emp in employee_list:
            try:
                # Check if employee still exists - using centralized function
                employee_details = get_employee_details(emp.employee)
                if not employee_details:
                    frappe.log_error(
                        "Employee {0} ({1}) no longer exists in the system".format(
                            emp.employee, emp.employee_name
                        ),
                        "Annual Tax Report Error",
                    )
                    summary["errors"] += 1
                    summary["details"].append(
                        {
                            "employee": emp.employee,
                            "employee_name": emp.employee_name,
                            "status": "Error",
                            "message": "Employee no longer exists",
                        }
                    )
                    continue

                # Check if employee tax summary exists - using cache
                cache_key = f"tax_summary:{emp.employee}:{year}"
                tax_summary_name = get_cached_value(cache_key)

                if tax_summary_name is None:
                    tax_summary_name = frappe.db.get_value(
                        "Employee Tax Summary", {"employee": emp.employee, "year": year}, "name"
                    )
                    # Cache result
                    cache_value(cache_key, tax_summary_name or False, CACHE_MEDIUM)

                if not tax_summary_name:
                    # Try to create tax summary if it doesn't exist - use cached results
                    try:
                        # Calculate tax summary using ter_logic
                        # Pass employee_details to avoid re-fetching
                        tax_data = hitung_pph_tahunan(emp.employee, year, employee_details)

                        # Create tax report document
                        create_annual_tax_report(emp.employee, year, tax_data, employee_details)

                        summary["processed"] += 1
                        summary["details"].append(
                            {
                                "employee": emp.employee,
                                "employee_name": emp.employee_name,
                                "status": "Success",
                                "message": "Tax report created",
                            }
                        )
                    except Exception as e:
                        frappe.log_error(
                            "Failed to create tax summary for {0} ({1}): {2}".format(
                                emp.employee, emp.employee_name, str(e)
                            ),
                            "Annual Tax Report Error",
                        )
                        summary["errors"] += 1
                        summary["details"].append(
                            {
                                "employee": emp.employee,
                                "employee_name": emp.employee_name,
                                "status": "Error",
                                "message": str(e)[:100],
                            }
                        )
                        continue
                else:
                    # Update existing tax summary
                    try:
                        update_existing_tax_report(
                            tax_summary_name, year, emp.employee, employee_details
                        )

                        summary["processed"] += 1
                        summary["details"].append(
                            {
                                "employee": emp.employee,
                                "employee_name": emp.employee_name,
                                "status": "Success",
                                "message": "Tax report updated",
                            }
                        )
                    except Exception as e:
                        frappe.log_error(
                            "Failed to update tax summary for {0} ({1}): {2}".format(
                                emp.employee, emp.employee_name, str(e)
                            ),
                            "Annual Tax Report Error",
                        )
                        summary["errors"] += 1
                        summary["details"].append(
                            {
                                "employee": emp.employee,
                                "employee_name": emp.employee_name,
                                "status": "Error",
                                "message": str(e)[:100],
                            }
                        )
                        continue

            except Exception as e:
                frappe.log_error(
                    "Error processing employee {0} ({1}): {2}".format(
                        emp.employee, emp.employee_name, str(e)
                    ),
                    "Annual Tax Report Error",
                )
                summary["errors"] += 1
                summary["details"].append(
                    {
                        "employee": emp.employee,
                        "employee_name": emp.employee_name,
                        "status": "Error",
                        "message": str(e)[:100],
                    }
                )
                continue

        # Log summary
        log_message = (
            "Tax report preparation completed for {0} (PMK 168/2023). "
            "Processed: {1}/{2}, "
            "Errors: {3}".format(
                year, summary["processed"], summary["total_employees"], summary["errors"]
            )
        )

        if summary["errors"] > 0:
            frappe.log_error(log_message, "Annual Tax Report Summary")
        else:
            frappe.log_error(log_message, "Annual Tax Report Success")

        frappe.msgprint(log_message)
        return summary

    except Exception as e:
        frappe.log_error(
            "Error preparing tax reports: {0}".format(str(e)), "Annual Tax Report Error"
        )
        frappe.throw(_("Error preparing tax reports: {0}").format(str(e)))


def create_annual_tax_report(
    employee: str,
    year: int,
    tax_data: Dict[str, Any],
    employee_details: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Create annual tax report document for an employee

    Args:
        employee: Employee ID
        year: Tax year
        tax_data: Tax calculation data
        employee_details: Pre-fetched employee details (optional)

    Returns:
        Generated report document name
    """
    try:
        # Get employee details if not provided - use centralized function with caching
        emp_doc = employee_details or get_employee_details(employee)

        if not emp_doc:
            # Check if Annual Tax Report DocType exists
            if not frappe.db.exists("DocType", "Annual Tax Report"):
                frappe.log_error(
                    "Annual Tax Report DocType does not exist. Cannot create report for {0}".format(
                        employee
                    ),
                    "Annual Tax Report Error",
                )
                return None

            # Get employee details
            emp_doc = get_employee_details(employee)

            if not emp_doc:
                frappe.log_error(
                    "Employee {0} not found".format(employee), "Annual Tax Report Error"
                )
                return None

        # Create report
        report_doc = frappe.new_doc("Annual Tax Report")
        report_doc.employee = employee
        report_doc.employee_name = emp_doc.get("employee_name", "")
        report_doc.year = year
        report_doc.company = emp_doc.get("company", "")

        # Check if we should treat this as a December run
        is_december_override = False
        if tax_data and "is_december_override" in tax_data:
            is_december_override = bool(tax_data.get("is_december_override", 0))
        
        # Add tax information from tax_data
        if tax_data:
            report_doc.gross_income = flt(tax_data.get("annual_income", 0))
            report_doc.net_income = flt(tax_data.get("annual_net", 0))
            report_doc.job_expense = flt(tax_data.get("biaya_jabatan", 0))
            report_doc.bpjs_deductions = flt(tax_data.get("bpjs_total", 0))
            report_doc.ptkp = flt(tax_data.get("ptkp", 0))
            report_doc.pkp = flt(tax_data.get("pkp", 0))
            report_doc.tax_paid = flt(tax_data.get("already_paid", 0))
            report_doc.annual_tax = flt(tax_data.get("annual_tax", 0))

            # Set tax status if field exists
            if hasattr(report_doc, "tax_status"):
                report_doc.tax_status = emp_doc.get("status_pajak", "TK0")
                
            # Set is_december_override flag if field exists
            if hasattr(report_doc, "is_december_override"):
                report_doc.is_december_override = is_december_override

            # Add TER information if field exists and TER is used
            if hasattr(report_doc, "ter_category") and tax_data.get("ter_used"):
                try:
                    # Map PTKP status to TER category using cached value
                    cache_key = f"ter_category:{emp_doc.get('status_pajak', 'TK0')}"
                    ter_category = get_cached_value(cache_key)

                    if ter_category is None:
                        ter_category = map_ptkp_to_ter_category(emp_doc.get("status_pajak", "TK0"))
                        cache_value(cache_key, ter_category, CACHE_LONG)

                    report_doc.ter_category = ter_category
                except Exception:
                    # Fallback to simpler mapping if function not available
                    if emp_doc.get("status_pajak") == "TK0":
                        report_doc.ter_category = TER_CATEGORY_A
                    else:
                        report_doc.ter_category = TER_CATEGORY_B

        # Insert document
        report_doc.insert(ignore_permissions=True)

        # Log success
        frappe.log_error(
            "Annual Tax Report created for {0} ({1}) - {2}".format(
                employee, emp_doc.get("employee_name", ""), year
            ),
            "Annual Tax Report Creation",
        )

        return report_doc.name

    except Exception as e:
        frappe.log_error(
            "Error creating annual tax report for {0}, year {1}: {2}".format(
                employee, year, str(e)
            ),
            "Annual Tax Report Creation Error",
        )
        raise


def update_existing_tax_report(
    report_name: str,
    year: int,
    employee: Optional[str] = None,
    employee_details: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Update an existing tax report with latest data

    Args:
        report_name: The name of the tax report document
        year: Tax year
        employee: Employee ID (optional if report has it)
        employee_details: Pre-fetched employee details (optional)

    Returns:
        True if updated successfully
    """
    try:
        # Get the report document
        report_doc = frappe.get_doc("Annual Tax Report", report_name)

        # Get employee ID from report if not provided
        employee = employee or report_doc.employee

        # Get employee details if not provided - use centralized function with caching
        emp_doc = employee_details or get_employee_details(employee)

        # Recalculate tax data using ter_logic
        tax_data = hitung_pph_tahunan(employee, year, emp_doc)

        # Check if we should treat this as a December run
        is_december_override = False
        if tax_data and "is_december_override" in tax_data:
            is_december_override = bool(tax_data.get("is_december_override", 0))

        # Update report with latest values
        if tax_data:
            report_doc.gross_income = flt(tax_data.get("annual_income", 0))
            report_doc.net_income = flt(tax_data.get("annual_net", 0))
            report_doc.job_expense = flt(tax_data.get("biaya_jabatan", 0))
            report_doc.bpjs_deductions = flt(tax_data.get("bpjs_total", 0))
            report_doc.ptkp = flt(tax_data.get("ptkp", 0))
            report_doc.pkp = flt(tax_data.get("pkp", 0))
            report_doc.tax_paid = flt(tax_data.get("already_paid", 0))
            report_doc.annual_tax = flt(tax_data.get("annual_tax", 0))
            
            # Update is_december_override flag if field exists
            if hasattr(report_doc, "is_december_override"):
                report_doc.is_december_override = is_december_override

            # Update TER information if field exists and TER is used
            if hasattr(report_doc, "ter_category") and tax_data.get("ter_used"):
                if emp_doc:
                    try:
                        # Map PTKP status to TER category using cached value
                        cache_key = f"ter_category:{emp_doc.get('status_pajak', 'TK0')}"
                        ter_category = get_cached_value(cache_key)

                        if ter_category is None:
                            ter_category = map_ptkp_to_ter_category(
                                emp_doc.get("status_pajak", "TK0")
                            )
                            cache_value(cache_key, ter_category, CACHE_LONG)

                        report_doc.ter_category = ter_category
                    except Exception:
                        # Silently ignore TER category update if it fails
                        pass

            # Update modification timestamps
            report_doc.modified = nowdate()

        # Save document
        report_doc.save(ignore_permissions=True)

        # Log success
        frappe.log_error(
            "Annual Tax Report updated for {0} ({1}) - {2}".format(
                employee, report_doc.employee_name, year
            ),
            "Annual Tax Report Update",
        )

        return True

    except Exception as e:
        frappe.log_error(
            "Error updating tax report {0}: {1}".format(report_name, str(e)),
            "Annual Tax Report Update Error",
        )
        raise


def find_december_payroll_entries(year: Optional[int] = None) -> list:
    """
    Find payroll entries that should be processed as December runs
    based on the is_december_run flag

    Args:
        year: Tax year to process. Defaults to current year.

    Returns:
        List of payroll entry documents that should be processed as December runs
    """
    try:
        # Validate parameters
        if not year:
            year = datetime.now().year
            
        # Find payroll entries marked with is_december_run=1
        entries = frappe.get_all(
            "Payroll Entry",
            filters={
                "docstatus": 1,
                "is_december_run": 1,
                "posting_date": ["between", [f"{year}-01-01", f"{year}-12-31"]],
            },
            fields=["name", "posting_date", "company"]
        )
        
        return entries
    except Exception as e:
        frappe.log_error(
            f"Error finding December payroll entries for year {year}: {str(e)}",
            "December Payroll Entry Search Error"
        )
        return []


def generate_form_1721_a1(
    employee: Optional[str] = None, year: Optional[int] = None, is_december_override: bool = False
) -> Dict[str, Any]:
    """
    Generate Form 1721-A1 (Annual Tax Form) for an employee or all employees
    according to PMK 168/2023 requirements

    Args:
        employee: Specific employee to generate form for
        year: Tax year to generate form for
        is_december_override: Flag to force December calculation mode

    Returns:
        Summary of generated forms
    """
    try:
        # Validate parameters
        if not year:
            year = datetime.now().year - 1  # Default to previous year
            frappe.msgprint(_("Tax year not specified, using previous year: {0}").format(year))

        # Process single employee if specified
        if employee:
            # Use centralized function to validate employee
            employee_details = get_employee_details(employee)
            if not employee_details:
                frappe.throw(_("Employee {0} not found").format(employee))

            # Generate form for one employee - pass pre-fetched employee details and December flag
            return create_1721_a1_form(employee, year, employee_details, is_december_override)

        # Get employee list from cache
        cache_key = f"active_employees:{year}"
        employees = get_cached_value(cache_key)

        if employees is None:
            # Process all active employees - fetch relevant fields only
            employees = frappe.get_all(
                "Employee",
                filters={"status": "Active"},
                fields=["name", "employee_name", "status_pajak"],
            )

            # Cache result for efficiency
            cache_value(cache_key, employees, CACHE_MEDIUM)

        summary = {"year": year, "total": len(employees), "success": 0, "failed": 0, "details": []}

        for emp in employees:
            try:
                # Map PTKP status to TER category for reference using cache
                cache_key = f"ter_category:{emp.get('status_pajak', 'TK0')}"
                ter_category = get_cached_value(cache_key)

                if ter_category is None:
                    ter_category = map_ptkp_to_ter_category(emp.get("status_pajak", "TK0"))
                    cache_value(cache_key, ter_category, CACHE_LONG)

                # Get full employee details for form creation
                emp_details = get_employee_details(emp.name)

                result = create_1721_a1_form(emp.name, year, emp_details, is_december_override)
                summary["success"] += 1
                summary["details"].append(
                    {
                        "employee": emp.name,
                        "employee_name": emp.employee_name,
                        "status_pajak": emp.get("status_pajak", "TK0"),
                        "ter_category": ter_category,
                        "status": "Success",
                        "message": "Form generated successfully",
                        "is_december_override": is_december_override,
                    }
                )
            except Exception as e:
                summary["failed"] += 1
                summary["details"].append(
                    {
                        "employee": emp.name,
                        "employee_name": emp.employee_name,
                        "status_pajak": emp.get("status_pajak", "TK0"),
                        "ter_category": ter_category if "ter_category" in locals() else "",
                        "status": "Failed",
                        "message": str(e)[:100],
                        "is_december_override": is_december_override,
                    }
                )
                continue

        # Log summary
        log_message = (
            "Form 1721-A1 generation completed for {0} (PMK 168/2023). "
            "Success: {1}/{2}, "
            "Failed: {3}, "
            "December Override: {4}".format(
                year, 
                summary["success"], 
                summary["total"], 
                summary["failed"],
                "Yes" if is_december_override else "No"
            )
        )

        if summary["failed"] > 0:
            frappe.log_error(log_message, "Form 1721-A1 Generation Summary")
        else:
            frappe.log_error(log_message, "Form 1721-A1 Generation Success")

        frappe.msgprint(log_message)
        return summary

    except Exception as e:
        frappe.log_error(
            "Error generating Form 1721-A1: {0}".format(str(e)), "Form 1721-A1 Generation Error"
        )
        frappe.throw(_("Error generating Form 1721-A1: {0}").format(str(e)))


def create_1721_a1_form(
    employee: str, 
    year: int, 
    employee_details: Optional[Dict[str, Any]] = None,
    is_december_override: bool = False
) -> Optional[str]:
    """
    Create Form 1721-A1 for a specific employee

    Args:
        employee: Employee ID
        year: Tax year
        employee_details: Pre-fetched employee details (optional)
        is_december_override: Flag to force December calculation mode

    Returns:
        Generated form document name or None if not implemented yet
    """
    # This is a stub for future implementation
    frappe.msgprint(
        _("Form 1721-A1 generation not fully implemented yet - PMK 168/2023 compliance pending")
    )

    # Log the action for audit purposes
    frappe.log_error(
        "Form 1721-A1 generation requested for employee {0}, year {1}, December override: {2}".format(
            employee, year, is_december_override
        ),
        "Form Generation Request",
    )

    return None


def process_december_flagged_runs(year: Optional[int] = None):
    """
    Process payroll entries that have is_december_run flag set to 1
    
    Args:
        year: Tax year to process. Defaults to current year.
    """
    try:
        # Validate parameters
        if not year:
            year = datetime.now().year
            
        # Find payroll entries marked for December processing
        december_entries = find_december_payroll_entries(year)
        
        if not december_entries:
            frappe.msgprint(_("No payroll entries marked for December processing found for year {0}").format(year))
            return
            
        # Process each payroll entry
        for entry in december_entries:
            try:
                frappe.msgprint(
                    _("Processing December-flagged payroll entry {0} from {1}").format(
                        entry.name, entry.posting_date
                    )
                )
                
                # Find salary slips generated from this payroll entry
                salary_slips = frappe.get_all(
                    "Salary Slip",
                    filters={
                        "payroll_entry": entry.name,
                        "docstatus": 1
                    },
                    fields=["name", "employee", "employee_name"]
                )
                
                if not salary_slips:
                    frappe.msgprint(
                        _("No salary slips found for payroll entry {0}").format(entry.name)
                    )
                    continue
                    
                # Log the action
                frappe.log_error(
                    "Processing {0} salary slips from December-flagged payroll entry {1}".format(
                        len(salary_slips), entry.name
                    ),
                    "December Run Processing"
                )
                
                # Process each salary slip for tax correction
                for slip in salary_slips:
                    try:
                        # Use employee details function for efficiency
                        employee_details = get_employee_details(slip.employee)
                        
                        # Calculate annual tax with December flag
                        tax_data = hitung_pph_tahunan(
                            slip.employee, 
                            year, 
                            employee_details,
                            {"is_december_override": 1}  # Pass December override flag
                        )
                        
                        # Update or create annual tax report
                        tax_summary_name = frappe.db.get_value(
                            "Employee Tax Summary", 
                            {"employee": slip.employee, "year": year}, 
                            "name"
                        )
                        
                        if tax_summary_name:
                            update_existing_tax_report(
                                tax_summary_name, 
                                year, 
                                slip.employee, 
                                employee_details
                            )
                        else:
                            create_annual_tax_report(
                                slip.employee, 
                                year, 
                                tax_data, 
                                employee_details
                            )
                            
                    except Exception as e:
                        frappe.log_error(
                            "Error processing salary slip {0} for employee {1} ({2}): {3}".format(
                                slip.name, slip.employee, slip.employee_name, str(e)
                            ),
                            "December Run Processing Error"
                        )
                        continue
                
                # Log completion
                frappe.log_error(
                    "Completed processing December-flagged payroll entry {0}".format(entry.name),
                    "December Run Processing"
                )
                
            except Exception as e:
                frappe.log_error(
                    "Error processing December-flagged payroll entry {0}: {1}".format(
                        entry.name, str(e)
                    ),
                    "December Run Processing Error"
                )
                continue
                
    except Exception as e:
        frappe.log_error(
            "Error in process_december_flagged_runs for year {0}: {1}".format(year, str(e)),
            "December Run Processing Error"
        )
        frappe.throw(_("Error processing December-flagged payroll runs: {0}").format(str(e)))
