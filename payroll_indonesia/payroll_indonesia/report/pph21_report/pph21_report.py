# Copyright (c) 2024, ITB Dev Team and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, flt
import json
from typing import Dict, List, Any, Tuple, Optional, Union

from payroll_indonesia.config import pph21_ter, pph21_ter_december


def execute(filters=None):
    """
    Main entry point for the PPh21 Report generation
    """
    if not filters:
        filters = {}

    validate_filters(filters)
    columns = get_columns()
    data = get_report_data(filters)

    return columns, data


def validate_filters(filters):
    """
    Validate and sanitize filters to ensure report runs correctly
    """
    if not filters.get("company"):
        frappe.throw(_("Company is required"))

    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("Period (From Date and To Date) is required"))

    try:
        from_date = getdate(filters.get("from_date"))
        to_date = getdate(filters.get("to_date"))
        if from_date > to_date:
            frappe.throw(_("From Date cannot be after To Date"))
    except Exception:
        frappe.throw(_("Invalid date format"))


def get_columns():
    """
    Define the columns for the PPh21 report
    """
    return [
        {
            "label": _("Employee"),
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 120
        },
        {
            "label": _("Employee Name"),
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 160
        },
        {
            "label": _("Tax Status"),
            "fieldname": "tax_status",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("Gross Income"),
            "fieldname": "bruto",
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "label": _("BPJS Deductions"),
            "fieldname": "bpjs_deductions",
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "label": _("Biaya Jabatan"),
            "fieldname": "biaya_jabatan",
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "label": _("Other Deductions"),
            "fieldname": "other_deductions",
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "label": _("Netto"),
            "fieldname": "netto",
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "label": _("PTKP (Monthly)"),
            "fieldname": "ptkp",
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "label": _("PKP"),
            "fieldname": "pkp",
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "label": _("Tax Rate"),
            "fieldname": "tax_rate",
            "fieldtype": "Data",
            "width": 80
        },
        {
            "label": _("PPh21"),
            "fieldname": "pph21",
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "label": _("Method"),
            "fieldname": "method",
            "fieldtype": "Data",
            "width": 100
        },
        {
            "label": _("Posting Date"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 100
        },
        {
            "label": _("Salary Slip"),
            "fieldname": "salary_slip",
            "fieldtype": "Link",
            "options": "Salary Slip",
            "width": 140
        }
    ]


def get_report_data(filters):
    """
    Fetch and process data for the PPh21 report based on filters
    """
    # Get salary slips within the date range
    salary_slips = get_salary_slips(filters)
    
    if not salary_slips:
        return []
    
    # Process salary slips to extract PPh21 data
    data = []
    for slip in salary_slips:
        row = process_salary_slip(slip)
        if row:
            data.append(row)
    
    return data


def get_salary_slips(filters):
    """
    Fetch salary slips based on the provided filters
    """
    conditions = get_conditions(filters)
    
    salary_slips = frappe.db.sql(
        """
        SELECT ss.name, ss.employee, ss.employee_name, ss.start_date, ss.end_date,
               ss.posting_date, ss.gross_pay, ss.total_deduction, ss.net_pay,
               ss.tax, ss.tax_type, ss.docstatus, ss.pph21_info,
               e.tax_status
        FROM `tabSalary Slip` ss
        LEFT JOIN `tabEmployee` e ON ss.employee = e.name
        WHERE ss.docstatus = 1 
        AND {conditions}
        ORDER BY ss.employee, ss.start_date
        """.format(conditions=conditions),
        filters,
        as_dict=1
    )
    
    return salary_slips


def get_conditions(filters):
    """
    Build SQL conditions based on filters
    """
    conditions = []
    
    if filters.get("company"):
        conditions.append("ss.company = %(company)s")
    
    if filters.get("from_date") and filters.get("to_date"):
        conditions.append("(ss.start_date BETWEEN %(from_date)s AND %(to_date)s OR ss.end_date BETWEEN %(from_date)s AND %(to_date)s)")
    
    if filters.get("employee"):
        conditions.append("ss.employee = %(employee)s")
        
    return " AND ".join(conditions)


def process_salary_slip(slip):
    """
    Extract and calculate PPh21 information from a salary slip
    """
    if not slip:
        return None
    
    # Try to parse the PPh21 info JSON string if available
    pph21_data = {}
    if slip.get("pph21_info"):
        try:
            pph21_data = json.loads(slip.get("pph21_info"))
        except (ValueError, TypeError):
            frappe.logger().error(f"Invalid PPh21 info JSON in Salary Slip {slip.name}")
    
    # Get components from the slip
    components = get_salary_slip_components(slip.name)
    
    bpjs_deductions = sum_bpjs_deductions(components)
    other_deductions = sum_other_deductions(components)
    
    # Get values from either the parsed JSON or calculate them
    bruto = pph21_data.get("bruto", slip.gross_pay or 0)
    ptkp = pph21_data.get("ptkp", 0)
    biaya_jabatan = pph21_data.get("biaya_jabatan", 0)
    netto = pph21_data.get("netto", 0)
    pkp = pph21_data.get("pkp", 0)
    tax_rate = pph21_data.get("rate", 0)
    pph21 = pph21_data.get("pph21", slip.tax or 0)
    
    # Set the calculation method
    method = "TER"
    if slip.get("tax_type") == "DECEMBER":
        method = "December"
    
    # Format the tax rate for display
    tax_rate_display = f"{tax_rate}%" if isinstance(tax_rate, (int, float)) else tax_rate
    
    return {
        "employee": slip.employee,
        "employee_name": slip.employee_name,
        "tax_status": slip.tax_status,
        "bruto": bruto,
        "bpjs_deductions": bpjs_deductions,
        "biaya_jabatan": biaya_jabatan,
        "other_deductions": other_deductions,
        "netto": netto,
        "ptkp": ptkp,
        "pkp": pkp,
        "tax_rate": tax_rate_display,
        "pph21": pph21,
        "method": method,
        "posting_date": slip.posting_date,
        "salary_slip": slip.name
    }


def get_salary_slip_components(salary_slip_name):
    """
    Fetch all components (earnings and deductions) for a salary slip
    """
    components = {}
    
    # Get earnings components
    earnings = frappe.db.sql(
        """
        SELECT sd.salary_component, sd.amount, sc.type, sc.is_tax_applicable, 
               sc.statistical_component, sc.do_not_include_in_total,
               sc.is_income_tax_component
        FROM `tabSalary Detail` sd
        LEFT JOIN `tabSalary Component` sc ON sd.salary_component = sc.name
        WHERE sd.parent = %s AND sd.parentfield = 'earnings'
        """,
        (salary_slip_name),
        as_dict=1
    )
    
    # Get deductions components
    deductions = frappe.db.sql(
        """
        SELECT sd.salary_component, sd.amount, sc.type, sc.statistical_component,
               sc.do_not_include_in_total, sc.is_income_tax_component
        FROM `tabSalary Detail` sd
        LEFT JOIN `tabSalary Component` sc ON sd.salary_component = sc.name
        WHERE sd.parent = %s AND sd.parentfield = 'deductions'
        """,
        (salary_slip_name),
        as_dict=1
    )
    
    components["earnings"] = earnings
    components["deductions"] = deductions
    
    return components


def sum_bpjs_deductions(components):
    """
    Sum all BPJS employee deductions from a list of components
    """
    total = 0
    for deduction in components.get("deductions", []):
        if "bpjs" in (deduction.get("salary_component") or "").lower() and "employee" in (deduction.get("salary_component") or "").lower():
            total += flt(deduction.get("amount", 0))
    return total


def sum_other_deductions(components):
    """
    Sum all non-BPJS, non-PPh21 deductions from a list of components
    """
    total = 0
    for deduction in components.get("deductions", []):
        component_name = (deduction.get("salary_component") or "").lower()
        if ("bpjs" not in component_name and 
            "pph 21" not in component_name and 
            "biaya jabatan" not in component_name):
            total += flt(deduction.get("amount", 0))
    return total