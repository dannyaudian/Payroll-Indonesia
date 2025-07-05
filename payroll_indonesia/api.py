# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 16:44:36 by dannyaudian

"""
Payroll Indonesia API endpoints.

Provides a RESTful API facade for accessing payroll functionality:
- BPJS Payment Summary operations
- Employee data retrieval
- Salary slip information
- Tax and BPJS calculations
"""

# Standard library imports
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

# Frappe imports
import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime

# Payroll Indonesia imports
from payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_services import (
    BPJSPaymentService,
    get_employee_bpjs_details,
    get_summary_for_period,
)

logger = logging.getLogger("payroll_api")


def send_response(
    status: str = "success",
    data: Optional[Union[Dict, List, str]] = None,
    error: Optional[Union[Dict, str]] = None,
    http_status_code: int = 200,
) -> Dict[str, Any]:
    """
    Standardized API response function.

    Args:
        status: Response status ('success' or 'error')
        data: Response data payload
        error: Error details if status is 'error'
        http_status_code: HTTP status code

    Returns:
        dict: Standardized response object
    """
    response = {"status": status}

    if data is not None:
        response["data"] = data

    if error is not None:
        response["error"] = error

    # Set HTTP status code if not 200
    if http_status_code != 200:
        frappe.local.response.http_status_code = http_status_code

    return response


@frappe.whitelist(allow_guest=False)
def create_payment_summary(
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
        dict: API response with status and data
    """
    try:
        # Input validation
        if not company:
            return send_response("error", error="Company is required", http_status_code=400)

        # Convert month and year to integers
        month = cint(month)
        year = cint(year)

        if month < 1 or month > 12:
            return send_response(
                "error", error="Month must be between 1 and 12", http_status_code=400
            )

        if year < 2000 or year > 2100:
            return send_response(
                "error", error="Year must be valid (between 2000 and 2100)", http_status_code=400
            )

        # Parse summary_details from JSON string if needed
        if isinstance(summary_details, str):
            try:
                summary_details = json.loads(summary_details)
            except json.JSONDecodeError:
                return send_response(
                    "error", error="Invalid JSON format for summary_details", http_status_code=400
                )

        # Create service instance
        service = BPJSPaymentService()

        # Delegate to service layer
        result = service.create_payment_summary(
            company=company,
            month=month,
            year=year,
            posting_date=posting_date,
            summary_details=summary_details,
        )

        # Return result
        return send_response("success", data=result)

    except frappe.ValidationError as e:
        logger.warning(f"Validation error in create_payment_summary: {str(e)}")
        return send_response("error", error=str(e), http_status_code=400)
    except frappe.DuplicateEntryError as e:
        logger.warning(f"Duplicate entry in create_payment_summary: {str(e)}")
        return send_response("error", error=str(e), http_status_code=409)
    except Exception as e:
        logger.error(f"Error in create_payment_summary: {str(e)}")
        return send_response(
            "error", error=f"An unexpected error occurred: {str(e)}", http_status_code=500
        )


@frappe.whitelist(allow_guest=False)
def get_payment_status(name: str) -> Dict[str, Any]:
    """
    Get status and details of a BPJS Payment Summary.

    Args:
        name: BPJS Payment Summary ID

    Returns:
        dict: API response with status and data
    """
    try:
        if not name:
            return send_response(
                "error", error="BPJS Payment Summary ID is required", http_status_code=400
            )

        # Create service instance
        service = BPJSPaymentService()

        # Delegate to service layer
        result = service.get_payment_status(name)

        # Return result
        return send_response("success", data=result)

    except frappe.DoesNotExistError as e:
        logger.warning(f"Document not found in get_payment_status: {str(e)}")
        return send_response("error", error=str(e), http_status_code=404)
    except frappe.PermissionError as e:
        logger.warning(f"Permission error in get_payment_status: {str(e)}")
        return send_response("error", error=str(e), http_status_code=403)
    except Exception as e:
        logger.error(f"Error in get_payment_status: {str(e)}")
        return send_response(
            "error", error=f"An unexpected error occurred: {str(e)}", http_status_code=500
        )


@frappe.whitelist(allow_guest=False)
def reconcile_payment_journal(
    payment_summary: str, journal_entry: Optional[str] = None, payment_entry: Optional[str] = None
) -> Dict[str, Any]:
    """
    Reconcile a BPJS Payment Summary with existing journal or payment entries.

    Args:
        payment_summary: BPJS Payment Summary ID
        journal_entry: Optional Journal Entry ID to link
        payment_entry: Optional Payment Entry ID to link

    Returns:
        dict: API response with status and data
    """
    try:
        if not payment_summary:
            return send_response(
                "error", error="BPJS Payment Summary ID is required", http_status_code=400
            )

        if not journal_entry and not payment_entry:
            return send_response(
                "error",
                error="Either Journal Entry or Payment Entry ID is required",
                http_status_code=400,
            )

        # Create service instance
        service = BPJSPaymentService()

        # Delegate to service layer
        result = service.reconcile_payment_journal(
            payment_summary=payment_summary,
            journal_entry=journal_entry,
            payment_entry=payment_entry,
        )

        # Return result
        return send_response("success", data=result)

    except frappe.ValidationError as e:
        logger.warning(f"Validation error in reconcile_payment_journal: {str(e)}")
        return send_response("error", error=str(e), http_status_code=400)
    except frappe.DoesNotExistError as e:
        logger.warning(f"Document not found in reconcile_payment_journal: {str(e)}")
        return send_response("error", error=str(e), http_status_code=404)
    except Exception as e:
        logger.error(f"Error in reconcile_payment_journal: {str(e)}")
        return send_response(
            "error", error=f"An unexpected error occurred: {str(e)}", http_status_code=500
        )


@frappe.whitelist(allow_guest=False)
def get_employee_bpjs_data(
    employee: str = None, company: str = None, from_date: str = None, to_date: str = None
) -> Dict[str, Any]:
    """
    Get BPJS contribution data for an employee or company.

    Args:
        employee: Optional employee ID
        company: Optional company name
        from_date: Optional start date for data filtering
        to_date: Optional end date for data filtering

    Returns:
        dict: API response with status and data
    """
    try:
        # Input validation
        if not employee and not company:
            return send_response(
                "error", error="Either employee or company is required", http_status_code=400
            )

        # Delegate to service layer
        result = get_employee_bpjs_details(
            employee=employee, company=company, from_date=from_date, to_date=to_date
        )

        # Return result
        return send_response("success", data=result)

    except frappe.ValidationError as e:
        logger.warning(f"Validation error in get_employee_bpjs_data: {str(e)}")
        return send_response("error", error=str(e), http_status_code=400)
    except frappe.PermissionError as e:
        logger.warning(f"Permission error in get_employee_bpjs_data: {str(e)}")
        return send_response("error", error=str(e), http_status_code=403)
    except Exception as e:
        logger.error(f"Error in get_employee_bpjs_data: {str(e)}")
        return send_response(
            "error", error=f"An unexpected error occurred: {str(e)}", http_status_code=500
        )


@frappe.whitelist(allow_guest=False)
def create_payment_entry(summary: str) -> Dict[str, Any]:
    """
    Create a Payment Entry for a BPJS Payment Summary.

    Args:
        summary: BPJS Payment Summary ID

    Returns:
        dict: API response with status and data
    """
    try:
        if not summary:
            return send_response(
                "error", error="BPJS Payment Summary ID is required", http_status_code=400
            )

        # Create service instance
        service = BPJSPaymentService()

        # Delegate to service layer
        result = service.create_payment_entry(summary)

        # Return result
        return send_response("success", data={"name": result})

    except frappe.ValidationError as e:
        logger.warning(f"Validation error in create_payment_entry: {str(e)}")
        return send_response("error", error=str(e), http_status_code=400)
    except frappe.DoesNotExistError as e:
        logger.warning(f"Document not found in create_payment_entry: {str(e)}")
        return send_response("error", error=str(e), http_status_code=404)
    except Exception as e:
        logger.error(f"Error in create_payment_entry: {str(e)}")
        return send_response(
            "error", error=f"An unexpected error occurred: {str(e)}", http_status_code=500
        )


@frappe.whitelist(allow_guest=False)
def get_payment_summaries(
    company: str = None,
    month: int = None,
    year: int = None,
    status: str = None,
    docstatus: int = None,
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
        dict: API response with status and data
    """
    try:
        # Convert parameters
        if month:
            month = cint(month)
        if year:
            year = cint(year)
        if docstatus:
            docstatus = cint(docstatus)
        if limit:
            limit = min(cint(limit), 100)  # Cap at 100 for performance

        # Delegate to service layer
        result = get_summary_for_period(
            company=company, month=month, year=year, status=status, docstatus=docstatus, limit=limit
        )

        # Return result
        return send_response("success", data=result)

    except frappe.ValidationError as e:
        logger.warning(f"Validation error in get_payment_summaries: {str(e)}")
        return send_response("error", error=str(e), http_status_code=400)
    except frappe.PermissionError as e:
        logger.warning(f"Permission error in get_payment_summaries: {str(e)}")
        return send_response("error", error=str(e), http_status_code=403)
    except Exception as e:
        logger.error(f"Error in get_payment_summaries: {str(e)}")
        return send_response(
            "error", error=f"An unexpected error occurred: {str(e)}", http_status_code=500
        )
