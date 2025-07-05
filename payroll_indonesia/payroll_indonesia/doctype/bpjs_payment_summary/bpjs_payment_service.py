# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 16:58:59 by dannyaudian

"""
BPJS Payment Services module.

This module provides business logic services for BPJS Payment Summary operations,
isolating database operations and complex logic from the API layer.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, today, now_datetime

# Import the core service
from payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.payment_summary_service_core import (
    PaymentSummaryService,
)

logger = logging.getLogger("bpjs_payment_services")


class BPJSPaymentService:
    """
    Service class for BPJS Payment Summary operations.

    This class handles business logic for creating and managing BPJS Payment Summaries,
    delegating to the doctype-specific service when appropriate.
    """

    def create_payment_summary(
        self,
        company: str,
        month: int,
        year: int,
        posting_date: Optional[str] = None,
        summary_details: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new BPJS Payment Summary.

        Args:
            company: Company name
            month: Month (1-12)
            year: Year
            posting_date: Optional posting date (defaults to today)
            summary_details: Optional list of employee details to include

        Returns:
            dict: Created BPJS Payment Summary information

        Raises:
            frappe.ValidationError: If input validation fails
            frappe.DuplicateEntryError: If a payment summary already exists for the period
        """
        # Check for existing payment summary for this period
        existing = frappe.db.exists(
            "BPJS Payment Summary",
            {
                "company": company,
                "month": month,
                "year": year,
                "docstatus": ["<", 2],  # Not cancelled
            },
        )

        if existing:
            raise frappe.DuplicateEntryError(
                _(f"BPJS Payment Summary already exists for {month}/{year} in {company}")
            )

        # Create new BPJS Payment Summary
        doc = frappe.new_doc("BPJS Payment Summary")
        doc.company = company
        doc.month = month
        doc.year = year

        # Set posting date if provided, otherwise use today
        doc.posting_date = posting_date or today()

        # Add summary details if provided
        if summary_details:
            for detail in summary_details:
                doc.append("employee_details", detail)

        # Save document
        doc.insert()

        # Trigger recomputation of totals
        service = PaymentSummaryService(doc)
        service.recompute_totals()

        # Return basic information about the created document
        return {
            "name": doc.name,
            "company": doc.company,
            "month": doc.month,
            "year": doc.year,
            "posting_date": doc.posting_date,
            "status": doc.status,
            "total": doc.total,
        }

    def get_payment_status(self, name: str) -> Dict[str, Any]:
        """
        Get status and details of a BPJS Payment Summary.

        Args:
            name: BPJS Payment Summary ID

        Returns:
            dict: BPJS Payment Summary information

        Raises:
            frappe.DoesNotExistError: If the document does not exist
            frappe.PermissionError: If user lacks permission
        """
        # Check if document exists
        if not frappe.db.exists("BPJS Payment Summary", name):
            raise frappe.DoesNotExistError(_(f"BPJS Payment Summary {name} does not exist"))

        # Check permissions
        if not frappe.has_permission("BPJS Payment Summary", "read", name):
            raise frappe.PermissionError(_(f"No permission to access BPJS Payment Summary {name}"))

        # Get document
        doc = frappe.get_doc("BPJS Payment Summary", name)

        # Prepare response with key information
        result = {
            "name": doc.name,
            "company": doc.company,
            "month": doc.month,
            "year": doc.year,
            "posting_date": doc.posting_date,
            "status": doc.status,
            "docstatus": doc.docstatus,
            "total": doc.total,
            "payment_entry": doc.payment_entry,
            "journal_entry": doc.journal_entry,
            "creation": doc.creation,
            "modified": doc.modified,
        }

        # Add summary of employee details
        if hasattr(doc, "employee_details") and doc.employee_details:
            result["employee_count"] = len(doc.employee_details)
            result["total_employee"] = sum(
                flt(d.kesehatan_employee) + flt(d.jht_employee) + flt(d.jp_employee)
                for d in doc.employee_details
            )
            result["total_employer"] = sum(
                flt(d.kesehatan_employer)
                + flt(d.jht_employer)
                + flt(d.jp_employer)
                + flt(d.jkk)
                + flt(d.jkm)
                for d in doc.employee_details
            )

        # Add component summary
        if hasattr(doc, "komponen") and doc.komponen:
            result["components"] = [
                {"component": c.component, "amount": c.amount} for c in doc.komponen
            ]

        return result

    def reconcile_payment_journal(
        self,
        payment_summary: str,
        journal_entry: Optional[str] = None,
        payment_entry: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reconcile a BPJS Payment Summary with existing journal or payment entries.

        Args:
            payment_summary: BPJS Payment Summary ID
            journal_entry: Optional Journal Entry ID to link
            payment_entry: Optional Payment Entry ID to link

        Returns:
            dict: Updated BPJS Payment Summary information

        Raises:
            frappe.ValidationError: If validation fails
            frappe.DoesNotExistError: If any document does not exist
        """
        # Check if BPJS Payment Summary exists
        if not frappe.db.exists("BPJS Payment Summary", payment_summary):
            raise frappe.DoesNotExistError(
                _(f"BPJS Payment Summary {payment_summary} does not exist")
            )

        # Check if Journal Entry exists if provided
        if journal_entry and not frappe.db.exists("Journal Entry", journal_entry):
            raise frappe.DoesNotExistError(_(f"Journal Entry {journal_entry} does not exist"))

        # Check if Payment Entry exists if provided
        if payment_entry and not frappe.db.exists("Payment Entry", payment_entry):
            raise frappe.DoesNotExistError(_(f"Payment Entry {payment_entry} does not exist"))

        # Get BPJS Payment Summary
        doc = frappe.get_doc("BPJS Payment Summary", payment_summary)

        # Validate document status
        if doc.docstatus != 1:
            raise frappe.ValidationError(
                _(f"BPJS Payment Summary {payment_summary} must be submitted before reconciliation")
            )

        # Update references
        changed = False

        if journal_entry and doc.journal_entry != journal_entry:
            doc.db_set("journal_entry", journal_entry)
            changed = True

        if payment_entry and doc.payment_entry != payment_entry:
            doc.db_set("payment_entry", payment_entry)
            changed = True

        # Update status if needed
        if payment_entry and doc.status != "Paid":
            doc.db_set("status", "Paid")
            changed = True

        if changed:
            doc.db_set("modified", now_datetime())
            doc.db_set("modified_by", frappe.session.user)

        # Return updated document info
        return {
            "name": doc.name,
            "company": doc.company,
            "month": doc.month,
            "year": doc.year,
            "status": doc.status,
            "payment_entry": doc.payment_entry,
            "journal_entry": doc.journal_entry,
            "modified": doc.modified,
        }

    def create_payment_entry(self, summary: str) -> str:
        """
        Create a Payment Entry for a BPJS Payment Summary.

        Args:
            summary: BPJS Payment Summary ID

        Returns:
            str: Created Payment Entry ID

        Raises:
            frappe.ValidationError: If validation fails
            frappe.DoesNotExistError: If the document does not exist
        """
        # Check if BPJS Payment Summary exists
        if not frappe.db.exists("BPJS Payment Summary", summary):
            raise frappe.DoesNotExistError(_(f"BPJS Payment Summary {summary} does not exist"))

        # Get BPJS Payment Summary
        doc = frappe.get_doc("BPJS Payment Summary", summary)

        # Check if Payment Entry already exists
        if doc.payment_entry:
            if frappe.db.exists("Payment Entry", doc.payment_entry):
                return doc.payment_entry

        # Create PaymentSummaryService instance and delegate to it
        service = PaymentSummaryService(doc)
        payment_entry_name = service.create_payment_entry()

        if not payment_entry_name:
            raise frappe.ValidationError(_("Failed to create Payment Entry"))

        return payment_entry_name


def get_employee_bpjs_details(
    employee: Optional[str] = None,
    company: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get BPJS contribution data for an employee or company.

    Args:
        employee: Optional employee ID
        company: Optional company name
        from_date: Optional start date for data filtering
        to_date: Optional end date for data filtering

    Returns:
        dict: BPJS contribution data

    Raises:
        frappe.ValidationError: If validation fails
        frappe.PermissionError: If user lacks permission
    """
    # Build filters
    filters = {}

    if employee:
        filters["employee"] = employee

        # Check if employee exists
        if not frappe.db.exists("Employee", employee):
            raise frappe.ValidationError(_(f"Employee {employee} does not exist"))

        # Check permissions
        if not frappe.has_permission("Employee", "read", employee):
            raise frappe.PermissionError(_(f"No permission to access Employee {employee}"))

    if company:
        filters["company"] = company

        # Check if company exists
        if not frappe.db.exists("Company", company):
            raise frappe.ValidationError(_(f"Company {company} does not exist"))

    # Date filters for Salary Slip
    date_filters = {}
    if from_date:
        date_filters["start_date"] = [">=", from_date]
    if to_date:
        date_filters["end_date"] = ["<=", to_date]

    # Get salary slips
    slip_filters = {"docstatus": 1}  # Submitted
    slip_filters.update(filters)
    slip_filters.update(date_filters)

    salary_slips = frappe.get_all(
        "Salary Slip",
        filters=slip_filters,
        fields=["name", "employee", "employee_name", "start_date", "end_date"],
    )

    # Extract BPJS components from salary slips
    bpjs_data = []

    for slip in salary_slips:
        # Get BPJS components
        employee_components = frappe.get_all(
            "Salary Detail",
            filters={
                "parent": slip.name,
                "parentfield": "deductions",
                "salary_component": ["like", "%BPJS%"],
            },
            fields=["salary_component", "amount"],
        )

        employer_components = frappe.get_all(
            "Salary Detail",
            filters={
                "parent": slip.name,
                "parentfield": "earnings",
                "salary_component": ["like", "%BPJS%"],
                "statistical_component": 1,
            },
            fields=["salary_component", "amount"],
        )

        # Skip if no BPJS components
        if not employee_components and not employer_components:
            continue

        # Create entry for this slip
        entry = {
            "salary_slip": slip.name,
            "employee": slip.employee,
            "employee_name": slip.employee_name,
            "start_date": slip.start_date,
            "end_date": slip.end_date,
            "employee_contributions": {},
            "employer_contributions": {},
        }

        # Add employee contributions
        for comp in employee_components:
            entry["employee_contributions"][comp.salary_component] = comp.amount

        # Add employer contributions
        for comp in employer_components:
            entry["employer_contributions"][comp.salary_component] = comp.amount

        # Calculate totals
        entry["total_employee"] = sum(
            flt(amount) for amount in entry["employee_contributions"].values()
        )
        entry["total_employer"] = sum(
            flt(amount) for amount in entry["employer_contributions"].values()
        )
        entry["total"] = entry["total_employee"] + entry["total_employer"]

        bpjs_data.append(entry)

    # Return result
    return {
        "count": len(bpjs_data),
        "data": bpjs_data,
        "filters": {
            "employee": employee,
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
        },
    }


def get_summary_for_period(
    company: Optional[str] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    status: Optional[str] = None,
    docstatus: Optional[int] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Get list of BPJS Payment Summaries based on filters.

    Args:
        company: Optional company filter
        month: Optional month filter
        year: Optional year filter
        status: Optional status filter
        docstatus: Optional document status filter
        limit: Maximum number of records to return

    Returns:
        dict: List of BPJS Payment Summaries

    Raises:
        frappe.ValidationError: If validation fails
    """
    # Build filters
    filters = {}

    if company:
        filters["company"] = company

    if month:
        filters["month"] = month

    if year:
        filters["year"] = year

    if status:
        filters["status"] = status

    if docstatus is not None:
        filters["docstatus"] = docstatus

    # Get BPJS Payment Summaries
    summaries = frappe.get_all(
        "BPJS Payment Summary",
        filters=filters,
        fields=[
            "name",
            "company",
            "month",
            "year",
            "posting_date",
            "status",
            "docstatus",
            "total",
            "payment_entry",
            "journal_entry",
            "creation",
            "modified",
        ],
        limit=limit,
        order_by="modified desc",
    )

    # Return result
    return {
        "count": len(summaries),
        "data": summaries,
        "filters": {
            "company": company,
            "month": month,
            "year": year,
            "status": status,
            "docstatus": docstatus,
        },
    }
