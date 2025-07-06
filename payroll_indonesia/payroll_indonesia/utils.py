# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-03 04:15:22 by dannyaudian

"""
General Payroll Indonesia helpers: account, utils, and decorator.
Provides utility functions only, no business logic.
"""

import json
import logging
import functools
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar, cast, Union, List

import frappe
from frappe.utils import flt, now, get_site_path, cint

from payroll_indonesia.config.config import get_live_config

# Define what's publicly accessible
__all__ = [
    "calculate_bpjs",
    "get_or_create_account",
    "find_parent_account",
    "create_parent_liability_account",
    "create_parent_expense_account",
    "rupiah_format",
    "safe_int",
    "get_formatted_currency",
    "write_json_file_if_enabled",
    "cache_get_settings",
]

# Configure logger
logger = logging.getLogger("payroll_utils")
F = TypeVar("F", bound=Callable[..., Any])


def calculate_bpjs(
    base_salary: float, rate_percent: float, *, max_salary: Optional[float] = None
) -> int:
    """
    Backward-compat helper lazily importing real calculator to avoid circular imports.

    Args:
        base_salary: The base salary amount for calculation
        rate_percent: The BPJS rate percentage (e.g., 1.0 for 1%)
        max_salary: Optional maximum salary cap for the calculation

    Returns:
        int: The calculated BPJS amount as a rounded integer (IDR has no cents)
    """
    from payroll_indonesia.override.salary_slip.bpjs_calculator import (
        calculate_bpjs as _real_calc,  # noqa: F401
    )

    return _real_calc(base_salary, rate_percent, max_salary=max_salary)


def debug_log(message: str, context: Any = None) -> None:
    """
    Log a debug message with optional context.

    Args:
        message: Log message
        context: Optional context identifier or data
    """
    if context:
        logger.debug(f"[{context}] {message}")

        # For backward compatibility, print if context is provided
        current_time = now()
        print(f"[{current_time}] [{context}] {message}")
    else:
        logger.debug(message)


def safe_execute(default_value: Any = None, log_exception: bool = True) -> Callable[[F], F]:
    """
    Decorator to safely execute a function and handle exceptions.

    Args:
        default_value: Value to return if an exception occurs
        log_exception: Whether to log the exception

    Returns:
        Function decorator that catches exceptions and returns default_value
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_exception:
                    logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
                return default_value

        return cast(F, wrapper)

    return decorator


@safe_execute(default_value=None)
def get_or_create_account(
    company: str,
    account_name: str,
    account_type: str = "Payable",
    is_group: int = 0,
    root_type: Optional[str] = None,
    parent_account: Optional[str] = None,
) -> Optional[str]:
    """
    Get or create an Account, return full account name.

    Args:
        company: Company name
        account_name: Account name (without company suffix)
        account_type: Payable/Expense/Income/Asset/etc.
        is_group: 1 for group account, 0 otherwise
        root_type: Asset/Liability/Expense/Income
        parent_account: Optional parent account name

    Returns:
        str: Full account name, or None if failed
    """
    if not company or not account_name:
        logger.error("Both company and account_name are required")
        return None

    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        logger.error(f"Company {company} has no abbreviation")
        return None

    full_name = f"{account_name} - {abbr}"
    if frappe.db.exists("Account", {"name": full_name, "company": company}):
        logger.debug(f"Account {full_name} already exists")
        return full_name

    # Determine root_type if not provided
    if not root_type:
        root_type = determine_root_type(account_type)

    # Find parent account if not provided
    if not parent_account:
        parent_account = find_parent_account(company, account_type, root_type)
        if not parent_account:
            logger.error(f"Parent account not found for {account_name}")
            return None

    # Create account data
    acc_data = {
        "doctype": "Account",
        "account_name": account_name,
        "company": company,
        "parent_account": parent_account,
        "is_group": is_group,
        "root_type": root_type,
        "account_currency": frappe.get_cached_value("Company", company, "default_currency"),
    }

    if not is_group and account_type:
        acc_data["account_type"] = account_type

    # Create the account
    try:
        doc = frappe.get_doc(acc_data)
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        logger.info(f"Created account: {full_name}")
        return full_name
    except Exception as e:
        logger.error(f"Failed to create account {full_name}: {e}")
        return None


def determine_root_type(account_type: str) -> str:
    """
    Determine the root type based on account type.

    Args:
        account_type: The type of account

    Returns:
        str: The appropriate root type
    """
    if account_type in {"Payable", "Tax", "Receivable"}:
        return "Liability"
    elif account_type in {"Expense", "Expense Account"}:
        return "Expense"
    elif account_type in {"Income", "Income Account"}:
        return "Income"
    elif account_type == "Asset":
        return "Asset"
    else:
        return "Liability"


@safe_execute(default_value=None)
def find_parent_account(
    company: str, account_type: str, root_type: Optional[str] = None
) -> Optional[str]:
    """
    Find parent account based on type/root_type.

    Args:
        company: Company name
        account_type: Account type (Payable, Expense, etc.)
        root_type: Root type (Asset/Liability/Expense/Income)

    Returns:
        str: Parent account name, or None if not found
    """
    # Determine root_type if not provided
    if not root_type:
        root_type = determine_root_type(account_type)

    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        logger.error(f"Company {company} has no abbreviation")
        return None

    # Try to get parent accounts from config
    config = get_live_config()
    parent_candidates = config.get("parent_accounts", {}).get(root_type, [])

    # Use default candidates if not in config
    if not parent_candidates:
        parent_candidates = get_default_parent_candidates(root_type)

    # Try each candidate
    for candidate in parent_candidates:
        # Try without suffix
        acc = frappe.db.get_value(
            "Account",
            {"account_name": candidate, "company": company, "is_group": 1},
            "name",
        )
        if acc:
            return acc

        # Try with suffix
        acc_with_suffix = f"{candidate} - {abbr}"
        if frappe.db.exists("Account", acc_with_suffix):
            return acc_with_suffix

    # Try to find any parent account with matching root_type
    accounts = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "is_group": 1,
            "root_type": root_type,
        },
        order_by="lft",
        limit=1,
    )
    if accounts:
        return accounts[0].name

    # Try standard root accounts
    root_map = {
        "Asset": "Application of Funds (Assets)",
        "Liability": "Source of Funds (Liabilities)",
        "Expense": "Expenses",
        "Income": "Income",
        "Equity": "Equity",
    }
    root_acc = root_map.get(root_type)
    if root_acc:
        full_name = f"{root_acc} - {abbr}"
        if frappe.db.exists("Account", full_name):
            return full_name

    return None


def get_default_parent_candidates(root_type: str) -> list:
    """
    Get default parent account candidates based on root type.

    Args:
        root_type: The root type of the account

    Returns:
        list: List of potential parent account names
    """
    if root_type == "Liability":
        return ["Duties and Taxes", "Current Liabilities", "Accounts Payable"]
    elif root_type == "Expense":
        return ["Direct Expenses", "Indirect Expenses", "Expenses"]
    elif root_type == "Income":
        return ["Income", "Direct Income", "Indirect Income"]
    elif root_type == "Asset":
        return ["Current Assets", "Fixed Assets"]
    else:
        return []


@safe_execute(default_value="Rp 0")
def rupiah_format(amount: Any) -> str:
    """
    Format number as Rupiah (Rp) string.

    Args:
        amount: The amount to format

    Returns:
        str: Formatted amount as Rupiah
    """
    try:
        value = float(amount)
    except (ValueError, TypeError):
        value = 0.0
    return f"Rp {value:,.0f}".replace(",", ".")


@safe_execute(default_value=0)
def safe_int(val: Any, default: int = 0) -> int:
    """
    Safely convert a value to int, return default if failed.

    Args:
        val: Value to convert
        default: Default value to return if conversion fails

    Returns:
        int: Converted integer or default value
    """
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


@safe_execute(default_value="0.00")
def get_formatted_currency(value: Any, currency: Optional[str] = None) -> str:
    """
    Format a number as currency with thousands separator.

    Args:
        value: Numeric value to format
        currency: Currency symbol (optional)

    Returns:
        str: Formatted currency string
    """
    from frappe.utils import fmt_money

    # Get default currency if not provided
    if not currency:
        currency = frappe.defaults.get_global_default("currency")

    # Convert value to float
    try:
        numeric_value = flt(value)
    except (ValueError, TypeError):
        numeric_value = 0.0

    # Format as money with currency symbol
    return fmt_money(numeric_value, currency=currency)


@safe_execute(default_value=None)
def create_parent_liability_account(company: str) -> Optional[str]:
    """
    Create or get BPJS liability parent account.

    Args:
        company: Company name

    Returns:
        str: Full parent account name, or None if failed
    """
    logger.info(f"Creating BPJS liability parent account for company: {company}")

    abbr = frappe.db.get_value("Company", company, "abbr")
    account_name = f"Statutory Payables - {abbr}"

    if frappe.db.exists("Account", account_name):
        return account_name

    # Find parent account
    parent_account = find_parent_account(company, "Liability")

    # Create account
    account = frappe.new_doc("Account")
    account.account_name = "Statutory Payables"
    account.company = company
    account.parent_account = parent_account
    account.account_type = "Tax"
    account.is_group = 1
    account.root_type = "Liability"

    account.flags.ignore_permissions = True
    account.insert()

    return account.name


@safe_execute(default_value=None)
def create_parent_expense_account(company: str) -> Optional[str]:
    """
    Create or get BPJS expense parent account.

    Args:
        company: Company name

    Returns:
        str: Full parent account name, or None if failed
    """
    logger.info(f"Creating BPJS expense parent account for company: {company}")

    abbr = frappe.db.get_value("Company", company, "abbr")
    account_name = f"Employee Benefits - {abbr}"

    if frappe.db.exists("Account", account_name):
        return account_name

    # Find parent account
    parent_account = find_parent_account(company, "Expense")

    # Create account
    account = frappe.new_doc("Account")
    account.account_name = "Employee Benefits"
    account.company = company
    account.parent_account = parent_account
    account.account_type = "Expense Account"
    account.is_group = 1
    account.root_type = "Expense"

    account.flags.ignore_permissions = True
    account.insert()

    return account.name


@safe_execute(log_exception=True)
def write_json_file_if_enabled(doc) -> bool:
    """
    Write settings to a JSON file if enabled.

    Args:
        doc: Document instance with settings data

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Check if sync to defaults.json is enabled
        sync_to_defaults = getattr(doc, "sync_to_defaults", False)
        if not sync_to_defaults:
            logger.debug("Sync to defaults.json is disabled")
            return False

        # Get app path
        app_path = frappe.get_app_path("payroll_indonesia")
        config_path = Path(app_path) / "config"
        defaults_file = config_path / "defaults.json"

        logger.debug(f"Syncing settings to defaults.json at {defaults_file}")

        # Ensure config directory exists
        if not config_path.exists():
            os.makedirs(config_path)
            logger.debug(f"Created config directory at {config_path}")

        # Prepare data to export
        export_data = {}

        # Add app info
        export_data["app_info"] = {
            "version": getattr(doc, "app_version", "1.0.0"),
            "last_updated": str(now()),
            "updated_by": frappe.session.user,
        }

        # Export common settings like BPJS, tax settings, etc.
        # This should be customized based on what needs to be exported

        # Write to file
        with open(defaults_file, "w") as f:
            json.dump(export_data, f, indent=4)

        logger.info(f"Successfully wrote settings to defaults.json by {frappe.session.user}")
        return True

    except Exception as e:
        logger.error(f"Error writing settings to defaults.json: {str(e)}")
        return False


@safe_execute(default_value=None)
def cache_get_settings():
    """
    Get cached Payroll Indonesia Settings or fetch if not in cache.

    Returns:
        Document: Payroll Indonesia Settings document
    """
    # Define cache key
    cache_key = "payroll_indonesia_settings"

    # Try to get from cache
    settings = frappe.cache().get_value(cache_key)

    # If not in cache, fetch and cache it
    if not settings:
        logger.debug("Settings not found in cache, fetching from database")
        settings = frappe.get_single("Payroll Indonesia Settings")

        # Cache for 5 minutes (300 seconds)
        frappe.cache().set_value(cache_key, settings, expires_in_sec=300)
        logger.debug("Cached settings for 300 seconds")
    else:
        logger.debug("Retrieved settings from cache")

    return settings


@safe_execute(default_value=0.0)
def get_ter_rate_from_child(category: str, annual_income: float) -> float:
    """
    Get TER rate for a specific category and income level from TER rate table.

    Args:
        category: TER category (TER A, TER B, TER C)
        annual_income: Annual taxable income

    Returns:
        float: Applicable TER rate (percentage)
    """
    # Get settings from cache
    settings = cache_get_settings()
    if not settings:
        logger.error("Could not retrieve Payroll Indonesia Settings")
        return 0.0

    # Default to fallback rate if defined, otherwise 5%
    fallback_rate = getattr(settings, "ter_fallback_rate", 5.0)

    # If no ter_rate_table, return fallback
    if not hasattr(settings, "ter_rate_table") or not settings.ter_rate_table:
        logger.warning(f"No TER rate table found, using fallback rate {fallback_rate}%")
        return fallback_rate

    # Filter rows by TER category
    category_rows = [row for row in settings.ter_rate_table if row.status_pajak == category]

    if not category_rows:
        logger.warning(
            f"No TER rates found for category {category}, using fallback rate {fallback_rate}%"
        )
        return fallback_rate

    # Sort by income_from to ensure proper order
    category_rows.sort(key=lambda x: flt(x.income_from))

    # Find applicable rate based on income
    for row in category_rows:
        if annual_income >= flt(row.income_from) and (
            cint(row.is_highest_bracket) or annual_income <= flt(row.income_to)
        ):
            logger.debug(
                f"Found TER rate {flt(row.rate)}% for {category} at income {annual_income}"
            )
            return flt(row.rate)

    logger.warning(
        f"No matching TER bracket found for {category} at income {annual_income}, "
        f"using fallback {fallback_rate}%"
    )
    return fallback_rate


# For backward compatibility
create_account = get_or_create_account
