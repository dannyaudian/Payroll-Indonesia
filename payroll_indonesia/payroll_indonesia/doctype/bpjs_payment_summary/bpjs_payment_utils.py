# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-17 06:52:53 by dannyaudian

import frappe

# from frappe import _
from frappe.utils import flt, get_last_day, cint

# Import get_bpjs_accounts from bpjs_account_mapping
from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import (
    get_bpjs_accounts,
)


def debug_log(message):
    frappe.logger().debug(message)


@frappe.whitelist()
def fetch_from_salary_slip(summary):
    """
    Fetches BPJS data from Salary Slips and updates the summary document

    Args:
        summary: BPJS Payment Summary document or name

    Returns:
        dict: Updated totals
    """
    if isinstance(summary, str):
        summary = frappe.get_doc("BPJS Payment Summary", summary)

    try:
        # Clear existing child table entries
        summary.set("summary_details", [])

        # Define date range based on period in summary
        start_date, end_date = get_period_dates(summary.month, summary.year)

        # Get all submitted salary slips in the period for this company
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "docstatus": 1,
                "company": summary.company,
                "start_date": [">=", start_date],
                "end_date": ["<=", end_date],
            },
            fields=["name", "employee", "employee_name"],
        )

        if not salary_slips:
            frappe.msgprint(("No submitted salary slips found for the selected period"))
            return {"total_employee": 0, "total_employer": 0, "grand_total": 0}

        # Aggregate totals
        total_employee = 0
        total_employer = 0

        # Process each salary slip
        for slip in salary_slips:
            # Get BPJS components from salary slip
            employee_share, employer_share = extract_bpjs_components(slip.name)

            # Skip if no BPJS components found
            if not employee_share and not employer_share:
                continue

            # Add row to child table
            summary.append(
                "summary_details",
                {
                    "employee": slip.employee,
                    "employee_name": slip.employee_name,
                    "salary_slip": slip.name,
                    "employee_share": employee_share,
                    "employer_share": employer_share,
                    "total": flt(employee_share) + flt(employer_share),
                },
            )

            # Update totals
            total_employee += flt(employee_share)
            total_employer += flt(employer_share)

        # Update summary document totals
        summary.total_employee = total_employee
        summary.total_employer = total_employer
        summary.grand_total = total_employee + total_employer

        # Save the document if not a new document
        if not summary.is_new():
            summary.save()
            frappe.msgprint(
                ("Successfully fetched BPJS data from {0} salary slips").format(
                    len(summary.summary_details)
                )
            )

        return {
            "total_employee": total_employee,
            "total_employer": total_employer,
            "grand_total": total_employee + total_employer,
        }

    except Exception as e:
        frappe.log_error(
            f"Error fetching BPJS data from salary slips: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Payment Summary Error",
        )
        frappe.throw(("Error fetching BPJS data from salary slips: {0}").format(str(e)))


def extract_bpjs_components(salary_slip):
    """
    Extracts BPJS component amounts from a salary slip

    Args:
        salary_slip: Name of the salary slip

    Returns:
        tuple: (employee_share, employer_share)
    """
    doc = frappe.get_doc("Salary Slip", salary_slip)

    employee_share = 0
    employer_share = 0

    # Process deductions (employee contributions)
    if doc.deductions:
        for deduction in doc.deductions:
            if "BPJS" in deduction.salary_component and "Employee" in deduction.salary_component:
                employee_share += flt(deduction.amount)

    # Process earnings (employer contributions)
    if doc.earnings:
        for earning in doc.earnings:
            if "BPJS" in earning.salary_component and "Employer" in earning.salary_component:
                employer_share += flt(earning.amount)

    return employee_share, employer_share


def get_period_dates(month, year):
    """
    Get start and end dates for a given month and year

    Args:
        month: Month (1-12)
        year: Year

    Returns:
        tuple: (start_date, end_date)
    """
    month = cint(month)
    year = cint(year)

    if month < 1 or month > 12:
        frappe.throw(("Month must be between 1 and 12"))

    start_date = f"{year}-{month:02d}-01"
    end_date = get_last_day(start_date)

    return start_date, end_date


@frappe.whitelist()
def create_payment_entry(summary):
    """
    Creates a Payment Entry for the BPJS Payment Summary

    Args:
        summary: BPJS Payment Summary document or name

    Returns:
        str: Name of the created Payment Entry
    """
    if isinstance(summary, str):
        summary = frappe.get_doc("BPJS Payment Summary", summary)

    try:
        # Check if payment entry already exists
        if summary.payment_entry:
            frappe.msgprint(("Payment Entry {0} already exists").format(summary.payment_entry))
            return summary.payment_entry

        # Check if summary has been submitted
        if summary.docstatus != 1:
            frappe.throw(("BPJS Payment Summary must be submitted before creating a Payment Entry"))

        # Check if summary has details
        if not summary.summary_details:
            frappe.throw(
                ("No BPJS payment details found. Please fetch data from salary slips first.")
            )

        # Get BPJS accounts for the company
        try:
            accounts = get_bpjs_accounts(summary.company)
        except frappe.ValidationError as e:
            frappe.throw(str(e))

        # Get company default bank account
        default_bank_account = frappe.get_cached_value(
            "Company", summary.company, "default_bank_account"
        )

        if not default_bank_account:
            frappe.throw(("Default Bank Account not set for Company {0}").format(summary.company))

        # Create Payment Entry
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Pay"
        pe.mode_of_payment = "Bank"
        pe.paid_from = default_bank_account
        pe.company = summary.company
        pe.posting_date = summary.posting_date
        pe.party_type = "Supplier"

        # Get BPJS supplier
        bpjs_supplier = get_bpjs_supplier(summary.company)
        pe.party = bpjs_supplier

        # Set payment amounts
        pe.paid_amount = summary.grand_total
        pe.source_exchange_rate = 1.0
        pe.target_exchange_rate = 1.0
        pe.received_amount = summary.grand_total

        # Set reference information
        pe.reference_no = summary.name
        pe.reference_date = summary.posting_date

        # Add description
        month_name = get_month_name(summary.month)
        pe.remarks = f"BPJS Payment for {month_name} {summary.year}"

        # Add GL entries
        # Add employee expense
        if summary.total_employee > 0:
            pe.append(
                "deductions",
                {
                    "account": accounts["employee_expense"],
                    "cost_center": get_default_cost_center(summary.company),
                    "amount": summary.total_employee,
                },
            )

        # Add employer expense
        if summary.total_employer > 0:
            pe.append(
                "deductions",
                {
                    "account": accounts["employer_expense"],
                    "cost_center": get_default_cost_center(summary.company),
                    "amount": summary.total_employer,
                },
            )

        # Add payable account as target
        pe.paid_to = accounts["payable"]

        # Add reference to BPJS Payment Summary
        pe.append(
            "references",
            {
                "reference_doctype": "BPJS Payment Summary",
                "reference_name": summary.name,
                "total_amount": summary.grand_total,
                "allocated_amount": summary.grand_total,
            },
        )

        # Save and submit payment entry
        pe.insert()
        pe.submit()

        # Update BPJS Payment Summary with payment entry reference
        summary.db_set("payment_entry", pe.name)
        summary.db_set("status", "Paid")

        frappe.msgprint(("Payment Entry {0} created successfully").format(pe.name))
        return pe.name

    except Exception as e:
        frappe.log_error(
            f"Error creating Payment Entry for BPJS Payment Summary {summary.name}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Payment Entry Error",
        )
        frappe.throw(("Error creating Payment Entry: {0}").format(str(e)))


def get_bpjs_supplier(company):
    """
    Get or create BPJS supplier

    Args:
        company: Company name

    Returns:
        str: Supplier name
    """
    supplier_name = "BPJS"

    if not frappe.db.exists("Supplier", supplier_name):
        # Create BPJS supplier if it doesn't exist
        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = supplier_name
        supplier.supplier_group = "Services"
        supplier.supplier_type = "Company"
        supplier.country = "Indonesia"
        supplier.insert(ignore_permissions=True)

    return supplier_name


def get_default_cost_center(company):
    """
    Get default cost center for a company

    Args:
        company: Company name

    Returns:
        str: Cost center name
    """
    return frappe.get_cached_value("Company", company, "cost_center")


def get_month_name(month):
    """
    Get Indonesian month name from month number

    Args:
        month: Month number (1-12)

    Returns:
        str: Month name in Indonesian
    """
    month_names = [
        "Januari",
        "Februari",
        "Maret",
        "April",
        "Mei",
        "Juni",
        "Juli",
        "Agustus",
        "September",
        "Oktober",
        "November",
        "Desember",
    ]

    month = cint(month)
    if month < 1 or month > 12:
        return str(month)

    return month_names[month - 1]


def get_formatted_currency(value, currency=None):
    """
    Format a number as currency with thousands separator

    Args:
        value: Numeric value to format
        currency: Currency symbol (optional)

    Returns:
        str: Formatted currency string
    """
    from frappe.utils import flt, fmt_money

    # Get default currency if not provided
    if not currency:
        currency = frappe.defaults.get_global_default("currency")

    # Format as money with currency symbol
    return fmt_money(flt(value), currency=currency)
