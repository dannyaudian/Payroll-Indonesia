# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-16 09:51:40 by dannyaudian

import frappe
from frappe.utils import flt, fmt_money, now_datetime
import logging
import time
import re

# Configure logger for BPJS
logger = logging.getLogger("bpjs")

# Explicit exports
__all__ = [
    "debug_log",
    "validate_mapping",
    "on_update_mapping",
    "find_parent_account",
    "rupiah_format",
    "now_ms",
    "get_standardized_bpjs_account",
]


def debug_log(message, module_name="BPJS", trace=False):
    """
    Log debug message with timestamp and additional info

    Args:
        message (str): Message to log
        module_name (str): Module name for logging
        trace (bool): Whether to include traceback
    """
    timestamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    if trace:
        frappe.log_error(f"[{timestamp}] {message}", module_name)
    else:
        logger.debug(f"[{timestamp}] {message}")


def validate_mapping(doc, method=None):
    """
    Wrapper for BPJSAccountMapping.validate method

    Args:
        doc: BPJS Account Mapping document
        method: Method name (unused)
    """
    # Skip if already being validated
    if getattr(doc, "_validated", False):
        return

    # Mark as being validated to prevent recursion
    doc._validated = True

    # Call the instance methods
    if not getattr(doc, "flags", {}).get("ignore_validate"):
        doc.validate_duplicate_mapping()

    # Clean up flag
    doc._validated = False


def on_update_mapping(doc, method=None):
    """
    Wrapper for BPJSAccountMapping.on_update method

    Args:
        doc: BPJS Account Mapping document
        method: Method name (unused)
    """
    frappe.cache().delete_value(f"bpjs_mapping_{doc.company}")
    logger.info(f"Cleared cache for BPJS mapping of company {doc.company}")


def find_parent_account(account_type, company, company_abbr=None):
    """
    Find appropriate parent account for creating BPJS accounts

    Args:
        account_type (str): Account type ('Expense' or 'Payable')
        company (str): Company name
        company_abbr (str, optional): Company abbreviation

    Returns:
        str: Parent account name or None if not found
    """
    if not company_abbr:
        company_abbr = frappe.get_cached_value("Company", company, "abbr")

    parent_account = None

    try:
        if account_type == "Expense":
            # Try standardized account names first
            bpjs_expenses = f"BPJS Expenses - {company_abbr}"
            if frappe.db.exists("Account", bpjs_expenses):
                return bpjs_expenses

            employee_benefits = f"Employee Benefits Expense - {company_abbr}"
            if frappe.db.exists("Account", employee_benefits):
                return employee_benefits

            indirect_expenses = f"Indirect Expenses - {company_abbr}"
            if frappe.db.exists("Account", indirect_expenses):
                return indirect_expenses

            # Fallback to default expense account
            parent_account = frappe.db.get_value("Company", company, "default_expense_account")

        elif account_type == "Payable":
            # Try standardized account names first
            bpjs_payable = f"BPJS Payable - {company_abbr}"
            if frappe.db.exists("Account", bpjs_payable):
                return bpjs_payable

            statutory_payable = f"Statutory Payable - {company_abbr}"
            if frappe.db.exists("Account", statutory_payable):
                return statutory_payable

            # Fallback to default payable account
            parent_account = frappe.db.get_value("Company", company, "default_payable_account")

        return parent_account
    except Exception as e:
        logger.error(f"Error finding parent account ({account_type}) for {company}: {str(e)}")
        frappe.log_error(
            f"Error finding parent account: {str(e)}\n{frappe.get_traceback()}",
            "Parent Account Error",
        )
        return None


def rupiah_format(value, with_prefix=True, decimals=0):
    """
    Format a number as Indonesian Rupiah

    Args:
        value (float/int): Number to format
        with_prefix (bool): Whether to include 'Rp' prefix
        decimals (int): Number of decimal places

    Returns:
        str: Formatted Rupiah value
    """
    try:
        value = flt(value, decimals)
        formatted = fmt_money(value, precision=decimals, currency="IDR")

        # Replace decimal comma with period for consistency
        formatted = formatted.replace(",", ".")

        # Strip currency symbol if not using prefix
        if not with_prefix:
            formatted = re.sub(r"^IDR\s+", "", formatted)
        elif "IDR" in formatted:
            # Replace IDR with Rp
            formatted = formatted.replace("IDR", "Rp")

        return formatted
    except Exception as e:
        logger.error(f"Error formatting rupiah value {value}: {str(e)}")
        # Return simple formatted value as fallback
        return f"Rp {value:,.0f}" if with_prefix else f"{value:,.0f}"


def now_ms():
    """
    Get current timestamp in milliseconds

    Returns:
        int: Current timestamp in milliseconds
    """
    return int(time.time() * 1000)


def get_standardized_bpjs_account(bpjs_type, account_type, company):
    """
    Get standardized BPJS account name based on type and company

    Args:
        bpjs_type (str): BPJS type (Kesehatan, JHT, JP, JKK, JKM)
        account_type (str): Account type (Expense or Payable)
        company (str): Company name

    Returns:
        str: Standardized account name
    """
    try:
        company_abbr = frappe.get_cached_value("Company", company, "abbr")

        if account_type == "Expense":
            return f"BPJS {bpjs_type} Employer Expense - {company_abbr}"
        elif account_type == "Payable":
            return f"BPJS {bpjs_type} Payable - {company_abbr}"
        else:
            return f"BPJS {bpjs_type} - {company_abbr}"
    except Exception as e:
        logger.error(
            f"Error getting standardized BPJS account for {bpjs_type}, {account_type}: {str(e)}"
        )
        return None
