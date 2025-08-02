# Copyright (c) 2024, ITB Dev Team and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, flt
from typing import Dict, List, Any, Tuple, Optional, Union


def execute(filters=None):
    """
    Main entry point for the BPJS Report generation
    """
    if not filters:
        filters = {}

    validate_filters(filters)
    columns = get_columns()
    data, summary = get_report_data(filters)

    # Add employer and employee total rows
    if data and summary:
        data.append({})  # Empty row as separator
        
        # Employer contribution summary
        employer_row = {
            "employee_name": "Total Employer Contribution",
            "bpjs_kesehatan_employer": summary.get("bpjs_kesehatan_employer", 0),
            "bpjs_jht_employer": summary.get("bpjs_jht_employer", 0),
            "bpjs_jp_employer": summary.get("bpjs_jp_employer", 0),
            "bpjs_jkk": summary.get("bpjs_jkk", 0),
            "bpjs_jkm": summary.get("bpjs_jkm", 0),
            "total_employer": summary.get("total_employer", 0)
        }
        data.append(employer_row)
        
        # Employee contribution summary
        employee_row = {
            "employee_name": "Total Employee Contribution",
            "bpjs_kesehatan_employee": summary.get("bpjs_kesehatan_employee", 0),
            "bpjs_jht_employee": summary.get("bpjs_jht_employee", 0),
            "bpjs_jp_employee": summary.get("bpjs_jp_employee", 0),
            "total_employee": summary.get("total_employee", 0)
        }
        data.append(employee_row)

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
    Define the columns for the BPJS report
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
            "label": _("BPJS Kesehatan (Employer)"),
            "fieldname": "bpjs_kesehatan_employer",
            "fieldtype": "Currency",
            "width": 170
        },
        {
            "label": _("BPJS Kesehatan (Employee)"),
            "fieldname": "bpjs_kesehatan_employee",
            "fieldtype": "Currency",
            "width": 170
        },
        {
            "label": _("BPJS JHT (Employer)"),
            "fieldname": "bpjs_jht_employer",
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "label": _("BPJS JHT (Employee)"),
            "fieldname": "bpjs_jht_employee",
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "label": _("BPJS JP (Employer)"),
            "fieldname": "bpjs_jp_employer",
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "label": _("BPJS JP (Employee)"),
            "fieldname": "bpjs_jp_employee",
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "label": _("BPJS JKK"),
            "fieldname": "bpjs_jkk",
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "label": _("BPJS JKM"),
            "fieldname": "bpjs_jkm",
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "label": _("Total Employer"),
            "fieldname": "total_employer",
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "label": _("Total Employee"),
            "fieldname": "total_employee",
            "fieldtype": "Currency",
            "width": 130
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
    Fetch and process data for the BPJS report based on filters
    """
    # Get salary slips within the date range
    salary_slips = get_salary_slips(filters)
    
    if not salary_slips:
        return [], {}
    
    # Process salary slips to extract BPJS data
    data = []
    summary = {
        "bpjs_kesehatan_employer": 0,
        "bpjs_kesehatan_employee": 0,
        "bpjs_jht_employer": 0,
        "bpjs_jht_employee": 0,
        "bpjs_jp_employer": 0,
        "bpjs_jp_employee": 0,
        "bpjs_jkk": 0,
        "bpjs_jkm": 0,
        "total_employer": 0,
        "total_employee": 0
    }
    
    for slip in salary_slips:
        row = process_salary_slip_bpjs(slip)
        if row:
            data.append(row)
            
            # Update summary
            for key in summary:
                summary[key] += flt(row.get(key, 0))
    
    return data, summary


def get_salary_slips(filters):
    """
    Fetch salary slips based on the provided filters
    """
    conditions = get_conditions(filters)
    
    salary_slips = frappe.db.sql(
        """
        SELECT ss.name, ss.employee, ss.employee_name, ss.start_date, ss.end_date,
               ss.posting_date, ss.gross_pay, ss.docstatus
        FROM `tabSalary Slip` ss
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


def process_salary_slip_bpjs(slip):
    """
    Extract and calculate BPJS information from a salary slip
    """
    if not slip:
        return None
    
    # Get BPJS components from the slip
    bpjs_components = get_bpjs_components(slip.name)
    
    if not any(bpjs_components.values()):
        return None
    
    # Calculate totals
    total_employer = (
        bpjs_components.get("bpjs_kesehatan_employer", 0) +
        bpjs_components.get("bpjs_jht_employer", 0) +
        bpjs_components.get("bpjs_jp_employer", 0) +
        bpjs_components.get("bpjs_jkk", 0) +
        bpjs_components.get("bpjs_jkm", 0)
    )
    
    total_employee = (
        bpjs_components.get("bpjs_kesehatan_employee", 0) +
        bpjs_components.get("bpjs_jht_employee", 0) +
        bpjs_components.get("bpjs_jp_employee", 0)
    )
    
    return {
        "employee": slip.employee,
        "employee_name": slip.employee_name,
        "bpjs_kesehatan_employer": bpjs_components.get("bpjs_kesehatan_employer", 0),
        "bpjs_kesehatan_employee": bpjs_components.get("bpjs_kesehatan_employee", 0),
        "bpjs_jht_employer": bpjs_components.get("bpjs_jht_employer", 0),
        "bpjs_jht_employee": bpjs_components.get("bpjs_jht_employee", 0),
        "bpjs_jp_employer": bpjs_components.get("bpjs_jp_employer", 0),
        "bpjs_jp_employee": bpjs_components.get("bpjs_jp_employee", 0),
        "bpjs_jkk": bpjs_components.get("bpjs_jkk", 0),
        "bpjs_jkm": bpjs_components.get("bpjs_jkm", 0),
        "total_employer": total_employer,
        "total_employee": total_employee,
        "posting_date": slip.posting_date,
        "salary_slip": slip.name
    }


def get_bpjs_components(salary_slip_name):
    """
    Fetch all BPJS-related components for a salary slip
    """
    components = {
        "bpjs_kesehatan_employer": 0,
        "bpjs_kesehatan_employee": 0,
        "bpjs_jht_employer": 0,
        "bpjs_jht_employee": 0,
        "bpjs_jp_employer": 0,
        "bpjs_jp_employee": 0,
        "bpjs_jkk": 0,
        "bpjs_jkm": 0
    }
    
    # Get all salary details for the salary slip
    salary_details = frappe.db.sql(
        """
        SELECT sd.salary_component, sd.amount, sd.parentfield
        FROM `tabSalary Detail` sd
        WHERE sd.parent = %s 
        AND sd.salary_component LIKE '%%BPJS%%'
        AND sd.salary_component NOT LIKE '%%Contra%%'
        """,
        (salary_slip_name),
        as_dict=1
    )
    
    # Process each component and categorize it
    for detail in salary_details:
        component_name = detail.get("salary_component", "").lower()
        amount = flt(detail.get("amount", 0))
        
        if "kesehatan" in component_name:
            if "employer" in component_name:
                components["bpjs_kesehatan_employer"] = amount
            elif "employee" in component_name:
                components["bpjs_kesehatan_employee"] = amount
                
        elif "jht" in component_name:
            if "employer" in component_name:
                components["bpjs_jht_employer"] = amount
            elif "employee" in component_name:
                components["bpjs_jht_employee"] = amount
                
        elif "jp" in component_name:
            if "employer" in component_name:
                components["bpjs_jp_employer"] = amount
            elif "employee" in component_name:
                components["bpjs_jp_employee"] = amount
                
        elif "jkk" in component_name:
            components["bpjs_jkk"] = amount
            
        elif "jkm" in component_name:
            components["bpjs_jkm"] = amount
    
    return components