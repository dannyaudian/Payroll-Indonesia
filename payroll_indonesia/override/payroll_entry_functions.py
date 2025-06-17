# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-16 08:33:58 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate, date_diff, cint


def before_validate(doc, method=None):
    """
    Event hook that runs before validating a Payroll Entry document.
    This file is retained only for backward-compatible hook registration.

    Since all validation logic has been centralized in CustomPayrollEntry class,
    this simply calls doc.validate() to ensure proper validation flow.

    This file can be safely removed in future versions once all hooks
    are updated to use CustomPayrollEntry directly.

    Args:
        doc: The Payroll Entry document instance
        method: The method being called (not used)
    """
    try:
        # Call validate() which contains all centralized validation logic
        if hasattr(doc, "validate") and callable(doc.validate):
            doc.validate()
    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # Log unexpected errors
        frappe.log_error(
            "Error in before_validate hook for Payroll Entry {0}: {1}".format(
                doc.name if hasattr(doc, "name") else "New", str(e)
            ),
            "Payroll Entry Hook Error",
        )
        # This is not a user-initiated action, so throw to prevent silent failures
        frappe.throw(_("Error in payroll entry validation hook: {0}").format(str(e)))


def create_salary_slip(employee, payroll_entry, *, is_december_override=False):
    """
    Creates a salary slip for an employee based on the payroll entry.

    Args:
        employee: Employee details (dict with employee, employee_name, etc.)
        payroll_entry: Payroll Entry document
        is_december_override: Boolean flag for December processing (keyword-only argument)

    Returns:
        Salary Slip document
    """
    # Check if salary slip already exists
    existing_salary_slip = frappe.db.sql(
        """
        select name from `tabSalary Slip`
        where docstatus != 2
        and employee = %s
        and start_date >= %s
        and end_date <= %s
        and company = %s
    """,
        (
            employee.employee,
            payroll_entry.start_date,
            payroll_entry.end_date,
            payroll_entry.company,
        ),
    )

    if existing_salary_slip:
        return frappe.get_doc("Salary Slip", existing_salary_slip[0][0])

    # Create new salary slip
    slip = frappe.new_doc("Salary Slip")
    slip.salary_slip_based_on_timesheet = payroll_entry.salary_slip_based_on_timesheet
    slip.payroll_frequency = payroll_entry.payroll_frequency
    slip.start_date = payroll_entry.start_date
    slip.end_date = payroll_entry.end_date
    slip.employee = employee.employee
    slip.employee_name = employee.employee_name
    slip.company = payroll_entry.company
    slip.posting_date = payroll_entry.posting_date
    slip.payroll_entry = payroll_entry.name

    # Set the December override flag
    slip.is_december_override = int(is_december_override)

    # Get earnings and deductions
    get_emp_and_working_day_details(slip)

    # Set other salary slip fields
    if hasattr(payroll_entry, "salary_structure") and payroll_entry.salary_structure:
        slip.salary_structure = payroll_entry.salary_structure

    # Set payment days
    if hasattr(payroll_entry, "payment_days") and payroll_entry.payment_days:
        slip.payment_days = payroll_entry.payment_days

    # Set department if available
    if hasattr(employee, "department") and employee.department:
        slip.department = employee.department

    # Set designation if available
    if hasattr(employee, "designation") and employee.designation:
        slip.designation = employee.designation

    # Save and return the salary slip
    slip.insert()

    return slip


def get_emp_and_working_day_details(slip):
    """
    Calculates working days and payment days for a salary slip.
    Also pulls default earnings and deductions from salary structure.

    Args:
        slip: Salary Slip document
    """
    if slip.employment_type == "Intern" or slip.employment_type == "Apprentice":
        slip.payment_days = date_diff(slip.end_date, slip.start_date) + 1
        return

    # Get the employment details
    joining_date, relieving_date = frappe.get_cached_value(
        "Employee", slip.employee, ["date_of_joining", "relieving_date"]
    )

    # Get the payment days
    payment_days = get_payment_days(
        joining_date,
        relieving_date,
        slip.start_date,
        slip.end_date,
        slip.exclude_from_total_working_days,
    )

    # Set payment days
    slip.payment_days = payment_days

    # Get the salary structure
    if not slip.salary_structure:
        structure = get_salary_structure(
            slip.employee, slip.posting_date, slip.payroll_frequency, slip.company
        )
        if structure:
            slip.salary_structure = structure.name

    # Get earnings and deductions
    if slip.salary_structure:
        from erpnext.payroll.doctype.salary_structure.salary_structure import (
            get_salary_structure_details,
        )

        salary_structure_details = get_salary_structure_details(
            slip.salary_structure, slip.payroll_frequency, slip.employee
        )

        # Set earnings
        for earning in salary_structure_details.get("earnings", []):
            slip.append("earnings", earning)

        # Set deductions
        for deduction in salary_structure_details.get("deductions", []):
            slip.append("deductions", deduction)

        # Set other details
        if "ctc" in salary_structure_details:
            slip.ctc = salary_structure_details.ctc

        if "base" in salary_structure_details:
            slip.base = salary_structure_details.base


def get_payment_days(
    joining_date, relieving_date, start_date, end_date, exclude_from_total_working_days=0
):
    """
    Calculate payment days based on joining and relieving dates.

    Args:
        joining_date: Employee joining date
        relieving_date: Employee relieving date
        start_date: Payroll period start date
        end_date: Payroll period end date
        exclude_from_total_working_days: Days to exclude

    Returns:
        Payment days (float)
    """
    start_date = getdate(start_date)
    end_date = getdate(end_date)
    joining_date = getdate(joining_date) if joining_date else None
    relieving_date = getdate(relieving_date) if relieving_date else None

    # Adjust start date if employee joined after payroll start date
    if joining_date and joining_date > start_date:
        start_date = joining_date

    # Adjust end date if employee relieved before payroll end date
    if relieving_date and relieving_date < end_date:
        end_date = relieving_date

    # Calculate payment days
    payment_days = date_diff(end_date, start_date) + 1 - exclude_from_total_working_days
    return payment_days if payment_days > 0 else 0


def get_salary_structure(employee, posting_date, payroll_frequency, company):
    """
    Get active salary structure for an employee.

    Args:
        employee: Employee ID
        posting_date: Posting date
        payroll_frequency: Frequency of payroll
        company: Company

    Returns:
        Salary Structure document or None
    """
    # Get salary structure assignment
    structure_assignment = frappe.db.sql(
        """
        select salary_structure
        from `tabSalary Structure Assignment`
        where employee = %s
        and docstatus = 1
        and %s between from_date and IFNULL(to_date, '2199-12-31')
    """,
        (employee, posting_date),
        as_dict=True,
    )

    if structure_assignment:
        # Get salary structure
        structure = frappe.db.sql(
            """
            select name, docstatus
            from `tabSalary Structure`
            where name = %s
            and docstatus = 1
            and is_active = 'Yes'
            and company = %s
            and ifnull(payroll_frequency, '') = %s
        """,
            (structure_assignment[0].salary_structure, company, payroll_frequency),
            as_dict=True,
        )

        if structure:
            return frappe.get_doc("Salary Structure", structure[0].name)

    return None


def create_salary_slips_for_employees(employees, payroll_entry, publish_progress=True):
    """
    Creates salary slips for a list of employees

    Args:
        employees: List of employee details
        payroll_entry: Payroll Entry document
        publish_progress: Whether to publish progress updates

    Returns:
        List of created salary slips
    """
    salary_slips = []

    # Get December override from payroll entry
    # _is_december_override = False
    # if hasattr(payroll_entry, "should_run_as_december") and callable(
    #     payroll_entry.should_run_as_december
    # ):
    #     _is_december_override = payroll_entry.should_run_as_december()
    # elif hasattr(payroll_entry, "is_december_run"):
    #     _is_december_override = bool(payroll_entry.get("is_december_run"))

    # Create salary slips
    for i, emp in enumerate(employees):
        if publish_progress:
            frappe.publish_progress(i * 100 / len(employees), title=_("Creating Salary Slips..."))

        try:
            # Create args dict with is_december_override
            args = {
                "doctype": "Salary Slip",
                "employee": emp.employee,
                "employee_name": emp.employee_name,
                "company": payroll_entry.company,
                "posting_date": payroll_entry.posting_date,
                "payroll_frequency": payroll_entry.payroll_frequency,
                "start_date": payroll_entry.start_date,
                "end_date": payroll_entry.end_date,
                "payroll_entry": payroll_entry.name,
                "salary_slip_based_on_timesheet": payroll_entry.salary_slip_based_on_timesheet,
                "is_december_override": cint(payroll_entry.is_december_run),
            }

            # Add optional fields if available
            if hasattr(emp, "department") and emp.department:
                args["department"] = emp.department

            if hasattr(emp, "designation") and emp.designation:
                args["designation"] = emp.designation

            if hasattr(payroll_entry, "salary_structure") and payroll_entry.salary_structure:
                args["salary_structure"] = payroll_entry.salary_structure

            if hasattr(payroll_entry, "payment_days") and payroll_entry.payment_days:
                args["payment_days"] = payroll_entry.payment_days

            # Insert the document
            salary_slip = frappe.get_doc(args).insert()
            salary_slips.append(salary_slip.name)

            # Log creation
            frappe.db.commit()

        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(
                f"Error creating salary slip for {emp.employee}: {str(e)}",
                "Salary Slip Creation Error",
            )

    if publish_progress:
        frappe.publish_progress(100, title=_("Salary Slips Created"))

    return salary_slips


def submit_salary_slips(salary_slips, payroll_entry):
    """
    Submits created salary slips

    Args:
        salary_slips: List of salary slip names
        payroll_entry: Payroll Entry document

    Returns:
        Tuple of (submitted_ss, not_submitted_ss)
    """
    submitted_ss = []
    not_submitted_ss = []

    for i, ss_name in enumerate(salary_slips):
        frappe.publish_progress(i * 100 / len(salary_slips), title=_("Submitting Salary Slips..."))

        try:
            ss = frappe.get_doc("Salary Slip", ss_name)
            if ss.net_pay < 0:
                not_submitted_ss.append(ss_name)
            else:
                ss.submit()
                submitted_ss.append(ss_name)

        except Exception as e:
            frappe.log_error(
                f"Error submitting salary slip {ss_name}: {str(e)}", "Salary Slip Submission Error"
            )
            not_submitted_ss.append(ss_name)

    frappe.publish_progress(100, title=_("Salary Slips Submitted"))

    return submitted_ss, not_submitted_ss
