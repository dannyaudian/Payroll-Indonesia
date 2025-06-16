# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-16 09:36:49 by dannyaudian

import frappe
from frappe.utils import flt, now_datetime
import logging

# Import mapping helpers from bpjs_account_mapping
from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping import (
    get_mapping_for_company,
)

# Set up logger
logger = logging.getLogger(__name__)


def debug_log(message, module_name="BPJS Payment Summary", trace=False):
    """Log debug message with timestamp and additional info"""
    timestamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    if trace:
        frappe.log_error(f"[{timestamp}] {message}", module_name)
    else:
        logger.debug(f"[{timestamp}] {message}")


@frappe.whitelist()
def get_salary_slip_bpjs_data(salary_slip):
    """
    Extract BPJS data from a specific salary slip

    Args:
        salary_slip (str): Name of the salary slip

    Returns:
        dict: Dictionary containing BPJS amounts
    """
    if not salary_slip:
        return None

    try:
        # Get the salary slip document
        doc = frappe.get_doc("Salary Slip", salary_slip)

        bpjs_data = {
            "jht_employee": 0,
            "jp_employee": 0,
            "kesehatan_employee": 0,
            "jht_employer": 0,
            "jp_employer": 0,
            "kesehatan_employer": 0,
            "jkk": 0,
            "jkm": 0,
        }

        # Extract employee contributions from deductions
        if hasattr(doc, "deductions") and doc.deductions:
            for d in doc.deductions:
                if "BPJS Kesehatan" in d.salary_component and "Employee" not in d.salary_component:
                    bpjs_data["kesehatan_employee"] += flt(d.amount)
                elif "BPJS JHT" in d.salary_component and "Employee" not in d.salary_component:
                    bpjs_data["jht_employee"] += flt(d.amount)
                elif "BPJS JP" in d.salary_component and "Employee" not in d.salary_component:
                    bpjs_data["jp_employee"] += flt(d.amount)
                # Support alternative naming with "Employee" suffix
                elif "BPJS Kesehatan Employee" in d.salary_component:
                    bpjs_data["kesehatan_employee"] += flt(d.amount)
                elif "BPJS JHT Employee" in d.salary_component:
                    bpjs_data["jht_employee"] += flt(d.amount)
                elif "BPJS JP Employee" in d.salary_component:
                    bpjs_data["jp_employee"] += flt(d.amount)

        # Extract employer contributions from earnings
        if hasattr(doc, "earnings") and doc.earnings:
            for e in doc.earnings:
                if "BPJS Kesehatan Employer" in e.salary_component:
                    bpjs_data["kesehatan_employer"] += flt(e.amount)
                elif "BPJS JHT Employer" in e.salary_component:
                    bpjs_data["jht_employer"] += flt(e.amount)
                elif "BPJS JP Employer" in e.salary_component:
                    bpjs_data["jp_employer"] += flt(e.amount)
                elif "BPJS JKK" in e.salary_component:
                    bpjs_data["jkk"] += flt(e.amount)
                elif "BPJS JKM" in e.salary_component:
                    bpjs_data["jkm"] += flt(e.amount)

        return bpjs_data

    except Exception as e:
        logger.error(f"Error getting BPJS data from salary slip {salary_slip}: {str(e)}")
        frappe.log_error(
            f"Error getting BPJS data from salary slip {salary_slip}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Salary Slip Data Error",
        )
        return None


@frappe.whitelist()
def get_salary_slips_for_period(
    company, month, year, include_all_unpaid=False, from_date=None, to_date=None
):
    """
    Get salary slips for a specific period

    Args:
        company (str): Company name
        month (int): Month (1-12)
        year (int): Year
        include_all_unpaid (bool): If True, include all unpaid slips
        from_date (str, optional): Custom start date
        to_date (str, optional): Custom end date

    Returns:
        list: List of salary slips
    """
    try:
        filters = {"docstatus": 1, "company": company}

        if not include_all_unpaid:
            # Use date range based on month and year
            if from_date and to_date:
                filters.update({"start_date": [">=", from_date], "end_date": ["<=", to_date]})
            else:
                # Calculate first and last day of month
                first_day = f"{year}-{month:02d}-01"
                last_day = frappe.utils.get_last_day(first_day)

                filters.update({"start_date": ["between", [first_day, last_day]]})

        # Get salary slips
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters=filters,
            fields=[
                "name",
                "employee",
                "employee_name",
                "start_date",
                "end_date",
                "total_deduction",
                "gross_pay",
            ],
        )

        # If include_all_unpaid is True, filter out slips already linked to BPJS payments
        if include_all_unpaid:
            # Get list of salary slips already linked to BPJS payments
            linked_slips = frappe.get_all(
                "BPJS Payment Summary Detail", filters={"docstatus": 1}, fields=["salary_slip"]
            )
            linked_slip_names = [slip.salary_slip for slip in linked_slips if slip.salary_slip]

            # Filter out already linked slips
            salary_slips = [slip for slip in salary_slips if slip.name not in linked_slip_names]

        return salary_slips

    except Exception as e:
        logger.error(f"Error getting salary slips for {month}/{year} in {company}: {str(e)}")
        frappe.log_error(
            f"Error getting salary slips for {month}/{year} in {company}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Salary Slip Query Error",
        )
        return []


@frappe.whitelist()
def create_journal_entry(bpjs_summary_name, posting_date=None):
    """
    Create Journal Entry for BPJS Payment Summary

    Args:
        bpjs_summary_name (str): Name of the BPJS Payment Summary
        posting_date (str, optional): Custom posting date

    Returns:
        str: Name of the created journal entry or None if failed
    """
    try:
        if not bpjs_summary_name:
            frappe.throw("BPJS Payment Summary name is required")

        # Get the BPJS Payment Summary document
        bpjs_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary_name)

        # Skip if already has journal entry
        if hasattr(bpjs_doc, "journal_entry") and bpjs_doc.journal_entry:
            frappe.msgprint(f"Journal Entry {bpjs_doc.journal_entry} already exists")
            return bpjs_doc.journal_entry

        # Get BPJS Account Mapping
        try:
            mapping = get_mapping_for_company(bpjs_doc.company)
        except frappe.DoesNotExistError:
            frappe.throw(f"BPJS Account Mapping not found for company {bpjs_doc.company}")

        if not mapping:
            frappe.throw(f"BPJS Account Mapping not found for company {bpjs_doc.company}")

        # Get company default accounts
        company_default_accounts = frappe.get_cached_value(
            "Company",
            bpjs_doc.company,
            ["default_expense_account", "default_payable_account", "cost_center"],
            as_dict=1,
        )

        # Get BPJS settings
        bpjs_settings = frappe.get_single("BPJS Settings")

        # Create Journal Entry
        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.company = bpjs_doc.company
        je.posting_date = posting_date or bpjs_doc.posting_date

        # Format month name for description
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

        month_num = bpjs_doc.month
        if isinstance(month_num, str):
            try:
                month_num = int(month_num)
            except ValueError:
                month_num = 0

        month_name = (
            month_names[month_num - 1]
            if month_num >= 1 and month_num <= 12
            else str(bpjs_doc.month)
        )

        je.user_remark = f"BPJS Contributions for {month_name} {bpjs_doc.year}"

        # Calculate employee and employer contribution totals
        employee_total, employer_total = calculate_contribution_totals(bpjs_doc)

        # Get company abbreviation
        company_abbr = frappe.get_cached_value("Company", bpjs_doc.company, "abbr")

        # Add expense entries (debit)
        # First for employee contributions - expense to Salary Payable
        if employee_total > 0:
            je.append(
                "accounts",
                {
                    "account": company_default_accounts.default_payable_account,
                    "debit_in_account_currency": employee_total,
                    "reference_type": "BPJS Payment Summary",
                    "reference_name": bpjs_doc.name,
                    "cost_center": company_default_accounts.cost_center,
                },
            )

        # For employer contributions - expense to BPJS Expense parent account or fallback
        expense_account = None

        # Try to find BPJS Expenses parent account
        bpjs_expense_parent = f"BPJS Expenses - {company_abbr}"
        if frappe.db.exists("Account", bpjs_expense_parent):
            expense_account = bpjs_expense_parent

        # If not found, try settings or default
        if not expense_account:
            expense_account = (
                bpjs_settings.expense_account
                if hasattr(bpjs_settings, "expense_account") and bpjs_settings.expense_account
                else company_default_accounts.default_expense_account
            )

        if employer_total > 0:
            je.append(
                "accounts",
                {
                    "account": expense_account,
                    "debit_in_account_currency": employer_total,
                    "reference_type": "BPJS Payment Summary",
                    "reference_name": bpjs_doc.name,
                    "cost_center": company_default_accounts.cost_center,
                },
            )

        # Add liability entries (credit) from account_details
        if hasattr(bpjs_doc, "account_details") and bpjs_doc.account_details:
            for acc in bpjs_doc.account_details:
                je.append(
                    "accounts",
                    {
                        "account": acc.account,
                        "credit_in_account_currency": acc.amount,
                        "reference_type": "BPJS Payment Summary",
                        "reference_name": bpjs_doc.name,
                        "cost_center": company_default_accounts.cost_center,
                    },
                )
        else:
            frappe.throw("No account details found in the BPJS Payment Summary")

        # Save and submit journal entry
        je.insert()
        je.submit()

        # Update reference in BPJS Payment Summary
        bpjs_doc.db_set("journal_entry", je.name)
        bpjs_doc.db_set("status", "Submitted")

        frappe.msgprint(f"Journal Entry {je.name} created successfully")
        return je.name

    except Exception as e:
        logger.error(
            f"Error creating Journal Entry for BPJS Payment Summary {bpjs_summary_name}: {str(e)}"
        )
        frappe.log_error(
            f"Error creating Journal Entry for BPJS Payment Summary {bpjs_summary_name}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Journal Entry Error",
        )
        frappe.msgprint(f"Error creating Journal Entry: {str(e)}")
        return None


def calculate_contribution_totals(bpjs_doc):
    """
    Calculate employee and employer contribution totals from a BPJS Payment Summary document

    Args:
        bpjs_doc (Document): BPJS Payment Summary document

    Returns:
        tuple: (employee_total, employer_total)
    """
    employee_total = 0
    employer_total = 0

    if hasattr(bpjs_doc, "employee_details") and bpjs_doc.employee_details:
        for d in bpjs_doc.employee_details:
            # Sum up employee contributions
            employee_total += flt(d.kesehatan_employee) + flt(d.jht_employee) + flt(d.jp_employee)

            # Sum up employer contributions
            employer_total += (
                flt(d.kesehatan_employer)
                + flt(d.jht_employer)
                + flt(d.jp_employer)
                + flt(d.jkk)
                + flt(d.jkm)
            )

    return employee_total, employer_total


@frappe.whitelist()
def create_payment_entry(bpjs_summary_name, posting_date=None, payment_account=None):
    """
    Create Payment Entry for BPJS Payment Summary

    Args:
        bpjs_summary_name (str): Name of the BPJS Payment Summary
        posting_date (str, optional): Custom posting date
        payment_account (str, optional): Bank or cash account for payment

    Returns:
        str: Name of the created payment entry or None if failed
    """
    try:
        if not bpjs_summary_name:
            frappe.throw("BPJS Payment Summary name is required")

        # Get the BPJS Payment Summary document
        bpjs_doc = frappe.get_doc("BPJS Payment Summary", bpjs_summary_name)

        # Skip if already has payment entry
        if hasattr(bpjs_doc, "payment_entry") and bpjs_doc.payment_entry:
            frappe.msgprint(f"Payment Entry {bpjs_doc.payment_entry} already exists")
            return bpjs_doc.payment_entry

        # Validate if Journal Entry exists
        if not hasattr(bpjs_doc, "journal_entry") or not bpjs_doc.journal_entry:
            frappe.throw("Journal Entry must be created before creating Payment Entry")

        je = frappe.get_doc("Journal Entry", bpjs_doc.journal_entry)
        if je.docstatus != 1:
            frappe.throw("Journal Entry must be submitted before creating Payment Entry")

        # Get company default bank account if payment_account not provided
        if not payment_account:
            payment_account = frappe.get_cached_value(
                "Company", bpjs_doc.company, "default_bank_account"
            )
            if not payment_account:
                frappe.throw(f"Default Bank Account not set for Company {bpjs_doc.company}")

        # Get supplier
        supplier = "BPJS"
        if not frappe.db.exists("Supplier", supplier):
            frappe.throw(f"Supplier '{supplier}' does not exist")

        # Create Payment Entry
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Pay"
        pe.mode_of_payment = "Bank"
        pe.paid_from = payment_account
        pe.company = bpjs_doc.company
        pe.posting_date = posting_date or bpjs_doc.posting_date
        pe.party_type = "Supplier"
        pe.party = supplier
        pe.paid_amount = bpjs_doc.total
        pe.source_exchange_rate = 1.0
        pe.target_exchange_rate = 1.0
        pe.reference_no = bpjs_doc.name
        pe.reference_date = bpjs_doc.posting_date

        # Format month name for description
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

        month_num = bpjs_doc.month
        if isinstance(month_num, str):
            try:
                month_num = int(month_num)
            except ValueError:
                month_num = 0

        month_name = (
            month_names[month_num - 1]
            if month_num >= 1 and month_num <= 12
            else str(bpjs_doc.month)
        )

        pe.remarks = f"Payment for BPJS Contributions {month_name} {bpjs_doc.year}"

        # Add reference to Journal Entry
        pe.append(
            "references",
            {
                "reference_doctype": "Journal Entry",
                "reference_name": je.name,
                "total_amount": bpjs_doc.total,
                "allocated_amount": bpjs_doc.total,
            },
        )

        # Add reference to BPJS Payment Summary
        pe.append(
            "references",
            {
                "reference_doctype": "BPJS Payment Summary",
                "reference_name": bpjs_doc.name,
                "total_amount": bpjs_doc.total,
                "allocated_amount": bpjs_doc.total,
            },
        )

        # Save payment entry
        pe.insert()

        # Update reference in BPJS Payment Summary
        bpjs_doc.db_set("payment_entry", pe.name)
        bpjs_doc.db_set("status", "Paid")

        frappe.msgprint(f"Payment Entry {pe.name} created successfully")
        return pe.name

    except Exception as e:
        logger.error(
            f"Error creating Payment Entry for BPJS Payment Summary {bpjs_summary_name}: {str(e)}"
        )
        frappe.log_error(
            f"Error creating Payment Entry for BPJS Payment Summary {bpjs_summary_name}: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Payment Entry Error",
        )
        frappe.msgprint(f"Error creating Payment Entry: {str(e)}")
        return None
