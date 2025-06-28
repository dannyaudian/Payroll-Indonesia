# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-28 23:44:37 by dannyaudian

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, Union, cast

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime

# Import central configuration
from payroll_indonesia.config import get_config, get_live_config

# Import helper functions
from payroll_indonesia.frappe_helpers import (
    safe_execute,
    ensure_doc_exists,
    doc_exists
)

# Import constants
from payroll_indonesia.constants import (
    CACHE_MEDIUM,
    CACHE_LONG,
    BIAYA_JABATAN_PERCENT,
    BIAYA_JABATAN_MAX,
    TER_CATEGORY_A,
    TER_CATEGORY_B,
    TER_CATEGORY_C,
)

# Import cache utilities
from payroll_indonesia.utilities.cache_utils import (
    get_cached_value,
    cache_value,
    memoize_with_ttl,
)

# Configure logger
logger = logging.getLogger(__name__)

# Define exports
__all__ = [
    "debug_log",
    "get_settings",
    "find_parent_account",
    "create_account",
    "create_parent_liability_account",
    "create_parent_expense_account",
    "retry_bpjs_mapping",
    "get_bpjs_settings",
    "calculate_bpjs_contributions",
    "get_ptkp_settings",
    "get_spt_month",
    "get_pph21_settings",
    "get_pph21_brackets",
    "get_ter_category",
    "get_ter_rate",
    "should_use_ter",
    "create_tax_summary_doc",
    "get_ytd_tax_info",
    "get_ytd_totals",
    "get_ytd_totals_from_tax_summary",
    "get_employee_details",
    "is_december_run",
]


def debug_log(
    message: str, 
    context: str = "GL Setup", 
    max_length: int = 500, 
    trace: bool = False
):
    """
    Debug logging helper with consistent format for tracing and contextual information.

    Args:
        message: Message to log
        context: Context identifier for the log
        max_length: Maximum message length to avoid memory issues
        trace: Whether to include traceback
    """
    timestamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    
    # Always truncate for safety
    message = str(message)[:max_length]

    # Format with context
    log_message = f"[{timestamp}] [{context}] {message}"

    # Log at appropriate level
    logger.info(log_message)

    if trace:
        logger.info(f"[{timestamp}] [{context}] [TRACE] {frappe.get_traceback()[:max_length]}")


@safe_execute(default_value=None, log_exception=True)
def get_settings():
    """
    Get Payroll Indonesia Settings document, creating if it doesn't exist.
    
    Returns:
        The settings document or None on error
    """
    settings_name = "Payroll Indonesia Settings"
    
    if not doc_exists(settings_name, settings_name):
        # Create default settings
        settings = create_default_settings()
    else:
        settings = frappe.get_doc(settings_name, settings_name)
    
    return settings


@safe_execute(default_value={}, log_exception=True)
def create_default_settings():
    """
    Create default Payroll Indonesia Settings.
    
    Returns:
        The created settings document
    """
    # Get configuration defaults
    config = get_live_config()
    
    # Extract values with defaults as fallbacks
    bpjs = config.get('bpjs', {})
    tax = config.get('tax', {})
    defaults = config.get('defaults', {})
    struktur_gaji = config.get('struktur_gaji', {})
    
    settings = frappe.get_doc({
        "doctype": "Payroll Indonesia Settings",
        "app_version": "1.0.0",
        "app_last_updated": frappe.utils.now(),
        "app_updated_by": frappe.session.user,
        
        # BPJS defaults
        "kesehatan_employee_percent": bpjs.get("kesehatan_employee_percent", 1.0),
        "kesehatan_employer_percent": bpjs.get("kesehatan_employer_percent", 4.0),
        "kesehatan_max_salary": bpjs.get("kesehatan_max_salary", 12000000.0),
        "jht_employee_percent": bpjs.get("jht_employee_percent", 2.0),
        "jht_employer_percent": bpjs.get("jht_employer_percent", 3.7),
        "jp_employee_percent": bpjs.get("jp_employee_percent", 1.0),
        "jp_employer_percent": bpjs.get("jp_employer_percent", 2.0),
        "jp_max_salary": bpjs.get("jp_max_salary", 9077600.0),
        "jkk_percent": bpjs.get("jkk_percent", 0.24),
        "jkm_percent": bpjs.get("jkm_percent", 0.3),
        
        # Tax defaults
        "umr_default": tax.get("umr_default", 4900000.0),
        "biaya_jabatan_percent": tax.get("biaya_jabatan_percent", 5.0),
        "biaya_jabatan_max": tax.get("biaya_jabatan_max", 500000.0),
        "tax_calculation_method": tax.get("tax_calculation_method", "TER"),
        "use_ter": tax.get("use_ter", 1),
        
        # Default settings
        "default_currency": defaults.get("currency", "IDR"),
        "payroll_frequency": defaults.get("payroll_frequency", "Monthly"),
        "max_working_days_per_month": defaults.get("max_working_days_per_month", 22),
        "working_hours_per_day": defaults.get("working_hours_per_day", 8),
        
        # Salary structure
        "basic_salary_percent": struktur_gaji.get("basic_salary_percent", 75),
        "meal_allowance": struktur_gaji.get("meal_allowance", 750000.0),
        "transport_allowance": struktur_gaji.get("transport_allowance", 900000.0),
        "position_allowance_percent": struktur_gaji.get("position_allowance_percent", 7.5),
        
        # Parent account candidates
        "parent_account_candidates_liability": 
            "Duties and Taxes\nCurrent Liabilities\nAccounts Payable",
        "parent_account_candidates_expense": 
            "Direct Expenses\nIndirect Expenses\nExpenses",
    })

    # Insert with permission bypass
    settings.flags.ignore_permissions = True
    settings.flags.ignore_mandatory = True
    settings.insert(ignore_permissions=True)

    frappe.db.commit()
    return settings


@safe_execute(default_value=None, log_exception=True)
def find_parent_account(
    company: str,
    account_type: str,
    root_type: Optional[str] = None,
) -> Optional[str]:
    """
    Find appropriate parent account based on account type and root type.
    
    Args:
        company: Company name
        account_type: Type of account (Payable, Expense, Asset, etc.)
        root_type: Root type (Liability, Expense, Asset, Income)
                  If None, determined from account_type

    Returns:
        str: Parent account name if found, None otherwise
    """
    # Determine root_type if not provided
    if not root_type:
        root_type = _get_root_type_from_account_type(account_type)

    debug_log(
        f"Finding parent account for {account_type} (root_type: {root_type}) in company {company}",
        "Account Lookup",
    )

    # Get company abbreviation for formatting account names
    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        debug_log(f"Company {company} does not have an abbreviation", "Account Lookup Error")
        return None

    # Get candidate parent accounts from settings
    candidates = _get_parent_account_candidates(root_type)

    # Search for parent account from candidate list
    parent_account = _find_parent_from_candidates(company, candidates, abbr)

    # If no parent account found from candidates, try fallback
    if not parent_account:
        # Fallback: Get any group account with the correct root_type
        parent_account = _find_fallback_parent_account(company, root_type)

        if parent_account:
            debug_log(
                f"Using fallback parent account for {account_type}: {parent_account}",
                "Account Lookup",
            )
        else:
            # Ultimate fallback: Use company's default root accounts
            parent_account = _find_company_root_account(company, root_type)

            if parent_account:
                debug_log(
                    f"Using company root account for {account_type}: {parent_account}",
                    "Account Lookup",
                )
            else:
                debug_log(
                    f"Could not find parent account for {account_type} in company {company}",
                    "Account Lookup Error",
                )
                return None

    return parent_account


def _get_root_type_from_account_type(account_type: str) -> str:
    """
    Determine the root type based on account type.

    Args:
        account_type: Type of account

    Returns:
        str: Root type
    """
    if account_type in ["Direct Expense", "Indirect Expense", "Expense Account", "Expense"]:
        return "Expense"
    elif account_type in ["Payable", "Tax", "Receivable"]:
        return "Liability"
    elif account_type == "Asset":
        return "Asset"
    elif account_type in ["Direct Income", "Indirect Income", "Income Account"]:
        return "Income"

    # Default mapping
    mapping = {
        "Cost of Goods Sold": "Expense",
        "Bank": "Asset",
        "Cash": "Asset",
        "Stock": "Asset",
        "Fixed Asset": "Asset",
        "Chargeable": "Expense",
        "Warehouse": "Asset",
        "Stock Adjustment": "Expense",
        "Round Off": "Expense",
    }

    return mapping.get(account_type, "Liability")


def _get_parent_account_candidates(root_type: str) -> List[str]:
    """
    Get parent account candidates for the given root type.

    Args:
        root_type: Root type of account

    Returns:
        List[str]: List of candidate account names
    """
    # Get from config
    config = get_live_config()
    candidates = config.get("parent_account_candidates", {}).get(root_type, [])

    # If no candidates found in config, use defaults
    if not candidates:
        if root_type == "Liability":
            candidates = ["Duties and Taxes", "Current Liabilities", "Accounts Payable"]
        elif root_type == "Expense":
            candidates = ["Direct Expenses", "Indirect Expenses", "Expenses"]
        elif root_type == "Income":
            candidates = ["Income", "Direct Income", "Indirect Income"]
        elif root_type == "Asset":
            candidates = ["Current Assets", "Fixed Assets"]
        else:
            candidates = []

    return candidates


def _find_parent_from_candidates(
    company: str, 
    candidates: List[str], 
    abbr: str
) -> Optional[str]:
    """
    Find parent account from the list of candidates.

    Args:
        company: Company name
        candidates: List of candidate account names
        abbr: Company abbreviation

    Returns:
        str: Parent account name if found, None otherwise
    """
    for candidate in candidates:
        # First check exact account name
        account = frappe.db.get_value(
            "Account", 
            {"account_name": candidate, "company": company, "is_group": 1}, 
            "name"
        )

        if account:
            debug_log(f"Found parent account by name: {account}", "Account Lookup")
            return account

        # Then check with company suffix
        account_with_suffix = f"{candidate} - {abbr}"
        if frappe.db.exists("Account", account_with_suffix):
            debug_log(f"Found parent account with suffix: {account_with_suffix}", "Account Lookup")
            return account_with_suffix

    return None


def _find_fallback_parent_account(company: str, root_type: str) -> Optional[str]:
    """
    Find any group account with the correct root_type as fallback.

    Args:
        company: Company name
        root_type: Root type of account

    Returns:
        str: Parent account name if found, None otherwise
    """
    # Query for any group account with the correct root_type
    accounts = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 1, "root_type": root_type},
        order_by="lft",
        limit=1,
    )

    if accounts:
        return accounts[0].name

    return None


def _find_company_root_account(company: str, root_type: str) -> Optional[str]:
    """
    Find root account for the company based on root type.
    This is the ultimate fallback when no other parent account can be found.

    Args:
        company: Company name
        root_type: Root type of account

    Returns:
        str: Account name if found, None otherwise
    """
    # Standard root accounts in ERPNext
    root_accounts = {
        "Asset": "Application of Funds (Assets)",
        "Liability": "Source of Funds (Liabilities)",
        "Expense": "Expenses",
        "Income": "Income",
        "Equity": "Equity",
    }

    # Get company abbr
    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        return None

    # Try to find the root account
    root_account = root_accounts.get(root_type)
    if not root_account:
        return None

    # Check with company suffix
    full_name = f"{root_account} - {abbr}"
    if frappe.db.exists("Account", full_name):
        return full_name

    # Try without company suffix as last resort
    if frappe.db.exists("Account", root_account):
        return root_account

    return None


@safe_execute(default_value=None, log_exception=True)
def create_account(
    company: str,
    account_name: str,
    account_type: str,
    parent: Optional[str] = None,
    root_type: Optional[str] = None,
    is_group: int = 0,
) -> Optional[str]:
    """
    Create GL Account if not exists with standardized naming and enhanced validation.
    
    Args:
        company: Company name
        account_name: Account name without company abbreviation
        account_type: Account type (Payable, Expense, etc.)
        parent: Parent account name (if None, will be determined automatically)
        root_type: Root type (Asset, Liability, etc.). If None, determined from account_type.
        is_group: Whether the account is a group account (1) or not (0)

    Returns:
        str: Full account name if created or already exists, None otherwise
    """
    debug_log(
        f"Starting account creation: {account_name} in {company} (Type: {account_type})",
        "Account Creation",
    )

    # Normalize invalid account_type
    if account_type == "Expense":
        account_type = "Expense Account"

    # Validate company
    if not company or not account_name:
        debug_log("Company and account name are required for account creation", "Account Error")
        return None

    # Get company abbreviation
    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        debug_log(f"Company {company} does not have an abbreviation", "Account Error")
        return None

    # Ensure account name doesn't already include the company abbreviation
    pure_account_name = account_name.replace(f" - {abbr}", "")
    full_account_name = f"{pure_account_name} - {abbr}"

    # Check if account already exists
    if frappe.db.exists("Account", full_account_name):
        debug_log(f"Account {full_account_name} already exists", "Account Creation")

        # Verify account properties are correct
        account_doc = frappe.db.get_value(
            "Account",
            full_account_name,
            ["account_type", "parent_account", "company", "is_group"],
            as_dict=1,
        )

        # For group accounts, account_type might be None
        expected_type = None if is_group else account_type
        actual_type = account_doc.account_type

        # Log differences but don't change existing accounts
        if (
            (expected_type and actual_type != expected_type)
            or account_doc.company != company
            or cint(account_doc.is_group) != cint(is_group)
        ):
            debug_log(
                f"Account {full_account_name} exists but has different properties.\n"
                f"Expected: type={expected_type or 'None'}, is_group={is_group}.\n"
                f"Found: type={actual_type or 'None'}, is_group={account_doc.is_group}",
                "Account Warning",
            )

        return full_account_name

    # Determine root_type if not provided
    if not root_type:
        root_type = _get_root_type_from_account_type(account_type)

    # Find parent account if not provided
    if not parent:
        parent = find_parent_account(company, account_type, root_type)

        if not parent:
            debug_log(
                f"Could not find suitable parent account for {account_name} ({account_type})",
                "Account Error",
            )
            return None

    # Verify parent account exists
    if not frappe.db.exists("Account", parent):
        debug_log(f"Parent account {parent} does not exist", "Account Error")
        return None

    # Create account fields
    account_fields = {
        "doctype": "Account",
        "account_name": pure_account_name,
        "company": company,
        "parent_account": parent,
        "is_group": cint(is_group),
        "root_type": root_type,
        "account_currency": frappe.get_cached_value("Company", company, "default_currency"),
    }

    # Only add account_type for non-group accounts
    if not is_group and account_type:
        account_fields["account_type"] = account_type

    debug_log(
        f"Creating account: {full_account_name}\n"
        f"Fields: {json.dumps(account_fields, indent=2)}",
        "Account Creation",
    )

    # Create the account document
    doc = frappe.get_doc(account_fields)

    # Bypass permissions and mandatory checks
    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory = True
    doc.insert(ignore_permissions=True)

    # Commit database changes immediately
    frappe.db.commit()

    # Verify account was created
    if frappe.db.exists("Account", full_account_name):
        debug_log(f"Successfully created account: {full_account_name}", "Account Creation")
        return full_account_name
    else:
        debug_log(
            f"Failed to create account {full_account_name} despite no errors", "Account Error"
        )
        return None


@safe_execute(default_value=None, log_exception=True)
def create_parent_liability_account(company: str) -> Optional[str]:
    """
    Create or get parent liability account for BPJS accounts.

    Args:
        company: Company name

    Returns:
        str: Parent account name if created or already exists, None otherwise
    """
    # Validate company
    if not company:
        frappe.throw(_("Company is required to create parent liability account"))

    # Get settings for account name
    config = get_live_config()
    gl_accounts = config.get("gl_accounts", {})
    parent_accounts = gl_accounts.get("parent_accounts", {})
    
    # Get account name from config or use default
    account_name = "BPJS Payable"
    if "bpjs_payable" in parent_accounts:
        account_name = parent_accounts.get("bpjs_payable", {}).get("account_name", account_name)

    # Get company abbreviation
    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        debug_log(f"Company {company} does not have an abbreviation", "Account Error")
        return None

    full_account_name = f"{account_name} - {abbr}"

    # Check if account already exists
    if frappe.db.exists("Account", full_account_name):
        # Verify the account is a group account
        is_group = frappe.db.get_value("Account", full_account_name, "is_group")
        if not is_group:
            # Convert to group account if needed
            try:
                account_doc = frappe.get_doc("Account", full_account_name)
                account_doc.is_group = 1
                account_doc.flags.ignore_permissions = True
                account_doc.save()
                frappe.db.commit()
                debug_log(f"Updated {full_account_name} to be a group account", "Account Fix")
            except Exception as e:
                logger.error(
                    f"Could not convert {full_account_name} to group account: {str(e)}"
                )

        return full_account_name

    # Create parent account using centralized function
    return create_account(
        company=company,
        account_name=account_name,
        account_type="Payable",
        root_type="Liability",
        is_group=1,
    )


@safe_execute(default_value=None, log_exception=True)
def create_parent_expense_account(company: str) -> Optional[str]:
    """
    Create or get parent expense account for BPJS accounts.

    Args:
        company: Company name

    Returns:
        str: Parent account name if created or already exists, None otherwise
    """
    # Validate company
    if not company:
        frappe.throw(_("Company is required to create parent expense account"))

    # Get settings for account name
    config = get_live_config()
    gl_accounts = config.get("gl_accounts", {})
    parent_accounts = gl_accounts.get("parent_accounts", {})
    
    # Get account name from config or use default
    account_name = "BPJS Expenses"
    if "bpjs_expenses" in parent_accounts:
        account_name = parent_accounts.get("bpjs_expenses", {}).get("account_name", account_name)

    # Get company abbreviation
    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        debug_log(f"Company {company} does not have an abbreviation", "Account Error")
        return None

    full_account_name = f"{account_name} - {abbr}"

    # Check if account already exists
    if frappe.db.exists("Account", full_account_name):
        # Verify the account is a group account
        is_group = frappe.db.get_value("Account", full_account_name, "is_group")
        if not is_group:
            # Convert to group account if needed
            try:
                account_doc = frappe.get_doc("Account", full_account_name)
                account_doc.is_group = 1
                # Remove account_type as it's not allowed for group accounts
                account_doc.account_type = None
                account_doc.flags.ignore_permissions = True
                account_doc.save()
                frappe.db.commit()
                debug_log(f"Updated {full_account_name} to be a group account", "Account Fix")
            except Exception as e:
                logger.error(
                    f"Could not convert {full_account_name} to group account: {str(e)}"
                )

        return full_account_name

    # Create parent account using centralized function
    return create_account(
        company=company,
        account_name=account_name,
        account_type=None,  # Group accounts should not have account_type
        root_type="Expense",
        is_group=1,
    )


@safe_execute(log_exception=True)
def retry_bpjs_mapping(companies: List[str]) -> None:
    """
    Background job to retry failed BPJS mapping creation.
    Called via frappe.enqueue() from ensure_bpjs_mapping_for_all_companies.

    Args:
        companies: List of company names to retry mapping for
    """
    if not companies:
        return

    # Import conditionally to avoid circular imports
    module_path = (
        "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping"
    )
    try:
        module = frappe.get_module(module_path)
        create_default_mapping = getattr(module, "create_default_mapping", None)
    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to import create_default_mapping: {str(e)}")
        return

    if not create_default_mapping:
        logger.error("create_default_mapping function not found")
        return

    # Get account mapping from the BPJS module for each company
    for company in companies:
        try:
            if not doc_exists("BPJS Account Mapping", {"company": company}):
                debug_log(
                    f"Retrying BPJS Account Mapping creation for {company}",
                    "BPJS Mapping Retry",
                )

                # Get account mapping from bpjs_account_mapping module
                try:
                    # We'll use get_bpjs_accounts() for each company
                    bpjs_accounts = module.get_bpjs_accounts(company)
                    mapping_name = create_default_mapping(company, bpjs_accounts)
                except Exception as e:
                    debug_log(
                        f"Error getting BPJS accounts for {company}: {str(e)}",
                        "BPJS Mapping Retry Error",
                        trace=True,
                    )
                    mapping_name = create_default_mapping(company, {})

                if mapping_name:
                    logger.info(
                        f"Successfully created BPJS Account Mapping for {company} on retry"
                    )
                else:
                    logger.warning(
                        f"Failed again to create BPJS Account Mapping for {company}"
                    )
        except Exception as e:
            logger.error(
                f"Error creating BPJS Account Mapping for {company} on retry: {str(e)}"
            )


# BPJS Settings and Calculation Functions
@memoize_with_ttl(ttl=CACHE_MEDIUM)
def get_bpjs_settings() -> Dict[str, Any]:
    """
    Get BPJS settings from configuration with caching.

    Returns:
        dict: Dictionary containing structured BPJS settings
    """
    # Get settings from central configuration
    config = get_live_config()
    bpjs = config.get('bpjs', {})
    
    # Convert to structured format
    return {
        "kesehatan": {
            "employee_percent": flt(bpjs.get("kesehatan_employee_percent", 1.0)),
            "employer_percent": flt(bpjs.get("kesehatan_employer_percent", 4.0)),
            "max_salary": flt(bpjs.get("kesehatan_max_salary", 12000000)),
        },
        "jht": {
            "employee_percent": flt(bpjs.get("jht_employee_percent", 2.0)),
            "employer_percent": flt(bpjs.get("jht_employer_percent", 3.7)),
        },
        "jp": {
            "employee_percent": flt(bpjs.get("jp_employee_percent", 1.0)),
            "employer_percent": flt(bpjs.get("jp_employer_percent", 2.0)),
            "max_salary": flt(bpjs.get("jp_max_salary", 9077600)),
        },
        "jkk": {"percent": flt(bpjs.get("jkk_percent", 0.24))},
        "jkm": {"percent": flt(bpjs.get("jkm_percent", 0.3))},
    }


@safe_execute(default_value={}, log_exception=True)
def calculate_bpjs_contributions(salary, bpjs_settings=None):
    """
    Calculate BPJS contributions based on salary and settings.

    Args:
        salary (float): Base salary amount
        bpjs_settings (object, optional): BPJS Settings or dict. Will fetch if not provided.

    Returns:
        dict: Dictionary containing BPJS contribution details
    """
    # Validate input
    if salary is None:
        frappe.throw(_("Salary amount is required for BPJS calculation"))

    salary = flt(salary)
    if salary < 0:
        frappe.msgprint(
            _("Negative salary amount provided for BPJS calculation, using absolute value")
        )
        salary = abs(salary)

    # Get BPJS settings if not provided
    if not bpjs_settings:
        bpjs_settings = get_bpjs_settings()

    # Extract values based on settings structure
    # Start with BPJS Kesehatan
    kesehatan = bpjs_settings.get("kesehatan", {})
    kesehatan_employee_percent = flt(kesehatan.get("employee_percent", 1.0))
    kesehatan_employer_percent = flt(kesehatan.get("employer_percent", 4.0))
    kesehatan_max_salary = flt(kesehatan.get("max_salary", 12000000))

    # BPJS JHT
    jht = bpjs_settings.get("jht", {})
    jht_employee_percent = flt(jht.get("employee_percent", 2.0))
    jht_employer_percent = flt(jht.get("employer_percent", 3.7))

    # BPJS JP
    jp = bpjs_settings.get("jp", {})
    jp_employee_percent = flt(jp.get("employee_percent", 1.0))
    jp_employer_percent = flt(jp.get("employer_percent", 2.0))
    jp_max_salary = flt(jp.get("max_salary", 9077600))

    # BPJS JKK and JKM
    jkk = bpjs_settings.get("jkk", {})
    jkm = bpjs_settings.get("jkm", {})
    jkk_percent = flt(jkk.get("percent", 0.24))
    jkm_percent = flt(jkm.get("percent", 0.3))

    # Cap salaries at maximum thresholds
    kesehatan_salary = min(flt(salary), kesehatan_max_salary)
    jp_salary = min(flt(salary), jp_max_salary)

    # Calculate BPJS Kesehatan
    kesehatan_karyawan = kesehatan_salary * (kesehatan_employee_percent / 100)
    kesehatan_perusahaan = kesehatan_salary * (kesehatan_employer_percent / 100)

    # Calculate BPJS Ketenagakerjaan - JHT
    jht_karyawan = flt(salary) * (jht_employee_percent / 100)
    jht_perusahaan = flt(salary) * (jht_employer_percent / 100)

    # Calculate BPJS Ketenagakerjaan - JP
    jp_karyawan = jp_salary * (jp_employee_percent / 100)
    jp_perusahaan = jp_salary * (jp_employer_percent / 100)

    # Calculate BPJS Ketenagakerjaan - JKK and JKM
    jkk = flt(salary) * (jkk_percent / 100)
    jkm = flt(salary) * (jkm_percent / 100)

    # Return structured result
    return {
        "kesehatan": {
            "karyawan": kesehatan_karyawan,
            "perusahaan": kesehatan_perusahaan,
            "total": kesehatan_karyawan + kesehatan_perusahaan,
        },
        "ketenagakerjaan": {
            "jht": {
                "karyawan": jht_karyawan,
                "perusahaan": jht_perusahaan,
                "total": jht_karyawan + jht_perusahaan,
            },
            "jp": {
                "karyawan": jp_karyawan,
                "perusahaan": jp_perusahaan,
                "total": jp_karyawan + jp_perusahaan,
            },
            "jkk": jkk,
            "jkm": jkm,
        },
    }


# PPh 21 Settings functions
@memoize_with_ttl(ttl=CACHE_MEDIUM)
def get_pph21_settings() -> Dict[str, Any]:
    """
    Get PPh 21 settings from configuration with caching.

    Returns:
        dict: PPh 21 settings including calculation method and TER usage
    """
    # Get settings from central configuration
    config = get_live_config()
    tax = config.get('tax', {})
    
    # Extract relevant fields
    calculation_method = tax.get("tax_calculation_method", "Progressive")
    use_ter = cint(tax.get("use_ter", 0))

    return {
        "calculation_method": calculation_method,
        "use_ter": use_ter,
        "ptkp_settings": get_ptkp_settings(),
        "brackets": get_pph21_brackets(),
    }


@memoize_with_ttl(ttl=CACHE_LONG)  # PTKP values rarely change
def get_ptkp_settings() -> Dict[str, float]:
    """
    Get PTKP settings from configuration with caching.

    Returns:
        dict: Dictionary mapping tax status codes to PTKP values
    """
    config = get_live_config()
    ptkp = config.get("ptkp", {})
    
    # If we have values from config, use them
    if ptkp:
        return ptkp
        
    # Default PTKP values if not in config
    return {
        "TK0": 54000000,
        "TK1": 58500000,
        "TK2": 63000000,
        "TK3": 67500000,
        "K0": 58500000,
        "K1": 63000000,
        "K2": 67500000,
        "K3": 72000000,
        "HB0": 112500000,
        "HB1": 117000000,
        "HB2": 121500000,
        "HB3": 126000000,
    }


@memoize_with_ttl(ttl=CACHE_LONG)  # Tax brackets rarely change
def get_pph21_brackets() -> List[Dict[str, Any]]:
    """
    Get PPh 21 tax brackets from configuration with caching.

    Returns:
        list: List of tax brackets with income ranges and rates
    """
    config = get_live_config()
    brackets = config.get("tax_brackets", [])
    
    # If we have brackets from config, use them
    if brackets:
        # Sort by income_from
        brackets.sort(key=lambda x: x["income_from"])
        return brackets
        
    # Default brackets based on current regulations
    return [
        {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
        {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
        {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
        {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
        {"income_from": 5000000000, "income_to": 0, "tax_rate": 35},
    ]


@safe_execute(default_value=12, log_exception=True)
def get_spt_month() -> int:
    """
    Get the month for annual SPT calculation.

    Returns:
        int: Month number (1-12)
    """
    # Try to get from configuration
    config = get_live_config()
    tax = config.get('tax', {})
    spt_month = tax.get("spt_month", None)
    
    if spt_month and isinstance(spt_month, int) and 1 <= spt_month <= 12:
        return spt_month

    # Get from environment variable as fallback
    spt_month_str = os.environ.get("SPT_BULAN")

    if spt_month_str:
        try:
            spt_month = int(spt_month_str)
            # Validate month is in correct range
            if 1 <= spt_month <= 12:
                return spt_month
        except ValueError:
            pass

    return 12  # Default to December


# Helper function for December logic
def is_december_run(flag: int) -> bool:
    """
    Check if this is a December run based on provided flag.
    """
    result = bool(flag)
    if result:
        logger.info(f"December run flag detected: {flag} -> {result}")
    return result


@safe_execute(default_value=TER_CATEGORY_C, log_exception=True)
def get_ter_category(ptkp_status):
    """
    Map PTKP status to TER category using configuration.

    Args:
        ptkp_status (str): Tax status code (e.g., 'TK0', 'K1')

    Returns:
        str: Corresponding TER category
    """
    # Get mapping from configuration
    config = get_live_config()
    ptkp_ter_mapping = config.get("ptkp_to_ter_mapping", {})
    
    # Check mapping from config
    if ptkp_status in ptkp_ter_mapping:
        return ptkp_ter_mapping[ptkp_status]

    # Default mapping logic
    prefix = ptkp_status[:2] if len(ptkp_status) >= 2 else ptkp_status
    suffix = ptkp_status[2:] if len(ptkp_status) >= 3 else "0"

    if ptkp_status == "TK0":
        return TER_CATEGORY_A
    elif prefix == "TK" and suffix in ["1", "2", "3"]:
        return TER_CATEGORY_B
    elif prefix == "K" and suffix == "0":
        return TER_CATEGORY_B
    elif prefix == "K" and suffix in ["1", "2", "3"]:
        return TER_CATEGORY_C
    elif prefix == "HB":  # Single parent
        return TER_CATEGORY_C
    else:
        # Default to highest category
        return TER_CATEGORY_C


@safe_execute(default_value=0, log_exception=True)
def get_ter_rate(status_pajak, penghasilan_bruto):
    """
    Get TER rate for a specific tax status and income level.

    Args:
        status_pajak (str): Tax status (TK0, K0, etc)
        penghasilan_bruto (float): Gross income

    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    # Validate inputs
    if not status_pajak:
        status_pajak = "TK0"

    if not penghasilan_bruto:
        penghasilan_bruto = 0

    penghasilan_bruto = flt(penghasilan_bruto)
    if penghasilan_bruto < 0:
        penghasilan_bruto = abs(penghasilan_bruto)

    # Map PTKP status to TER category using new centralized function
    ter_category = get_ter_category(status_pajak)

    # Create cache key
    cache_key = f"ter_rate:{ter_category}:{int(penghasilan_bruto / 1000) * 1000}"  # Round to nearest 1000
    cached_rate = frappe.cache().get_value(cache_key)

    if cached_rate is not None:
        return cached_rate

    # Query from database
    if frappe.db.exists("DocType", "PPh 21 TER Table"):
        ter = frappe.db.sql(
            """
            SELECT rate
            FROM `tabPPh 21 TER Table`
            WHERE status_pajak = %s
              AND %s >= income_from
              AND (%s < income_to OR income_to = 0)
            ORDER BY income_from DESC
            LIMIT 1
        """,
            (ter_category, penghasilan_bruto, penghasilan_bruto),
            as_dict=1,
        )

        if ter:
            rate = flt(ter[0].rate) / 100.0
            frappe.cache().set_value(cache_key, rate, expires_in_sec=CACHE_MEDIUM)
            return rate

        # Try to find highest bracket
        ter = frappe.db.sql(
            """
            SELECT rate
            FROM `tabPPh 21 TER Table`
            WHERE status_pajak = %s
              AND is_highest_bracket = 1
            LIMIT 1
        """,
            (ter_category,),
            as_dict=1,
        )

        if ter:
            rate = flt(ter[0].rate) / 100.0
            frappe.cache().set_value(cache_key, rate, expires_in_sec=CACHE_MEDIUM)
            return rate

    # Default rates if not found
    if ter_category == TER_CATEGORY_A:
        rate = 0.05
    elif ter_category == TER_CATEGORY_B:
        rate = 0.10
    else:  # TER_CATEGORY_C
        rate = 0.15

    frappe.cache().set_value(cache_key, rate, expires_in_sec=CACHE_MEDIUM)
    return rate


@safe_execute(default_value=False, log_exception=True)
def should_use_ter(salary_slip=None, is_december_override=False):
    """
    Check if TER method should be used based on configuration.
    
    Args:
        salary_slip (str, optional): Salary slip name or object
        is_december_override (bool, optional): Flag to override December behavior

    Returns:
        bool: True if TER should be used, False otherwise
    """
    # December override should ALWAYS force progressive calculation (no TER)
    if is_december_run(is_december_override):
        logger.info("December override detected - forcing Progressive calculation (no TER)")
        return False

    # If salary slip provided, check its December override flag too
    if salary_slip:
        # Handle both string (salary slip name) and object
        if isinstance(salary_slip, str):
            slip_december_flag = frappe.db.get_value(
                "Salary Slip", salary_slip, "is_december_override"
            )
        else:
            slip_december_flag = getattr(salary_slip, "is_december_override", 0)

        if slip_december_flag:
            logger.info(
                "Salary slip has December override flag - forcing Progressive calculation"
            )
            return False

    # Get settings from configuration
    config = get_live_config()
    tax = config.get('tax', {})
    
    calc_method = tax.get("tax_calculation_method", "Progressive")
    use_ter = cint(tax.get("use_ter", 0))

    # Return TER setting only if not December
    result = calc_method == "TER" and use_ter

    logger.info(
        f"TER check result: {result} (method={calc_method}, use_ter={use_ter})"
    )
    return result


# YTD Functions - Consolidated for easier testing and reuse
@safe_execute(default_value=None, log_exception=True)
def get_employee_details(employee_id=None, salary_slip=None):
    """
    Get employee details from either employee ID or salary slip
    with efficient caching.

    Args:
        employee_id (str, optional): Employee ID
        salary_slip (str, optional): Salary slip name to extract employee ID from

    Returns:
        dict: Employee details
    """
    if not employee_id and not salary_slip:
        return None

    # If salary slip provided but not employee_id, extract it from salary slip
    if not employee_id and salary_slip:
        # Check cache for salary slip
        slip_cache_key = f"salary_slip:{salary_slip}"
        slip = get_cached_value(slip_cache_key)

        if slip is None:
            # Query employee directly from salary slip if not in cache
            employee_id = frappe.db.get_value("Salary Slip", salary_slip, "employee")

            if not employee_id:
                # Salary slip not found or doesn't have employee
                return None
        else:
            # Extract employee_id from cached slip
            employee_id = slip.employee

    # Verify employee exists
    ensure_doc_exists("Employee", employee_id)

    # Get employee details from cache or DB
    cache_key = f"employee_details:{employee_id}"
    employee_data = get_cached_value(cache_key)

    if employee_data is None:
        # Query employee document
        employee_doc = frappe.get_doc("Employee", employee_id)

        # Extract relevant fields for lighter caching
        employee_data = {
            "name": employee_doc.name,
            "employee_name": employee_doc.employee_name,
            "company": employee_doc.company,
            "status_pajak": getattr(employee_doc, "status_pajak", "TK0"),
            "npwp": getattr(employee_doc, "npwp", ""),
            "ktp": getattr(employee_doc, "ktp", ""),
            "ikut_bpjs_kesehatan": cint(getattr(employee_doc, "ikut_bpjs_kesehatan", 1)),
            "ikut_bpjs_ketenagakerjaan": cint(
                getattr(employee_doc, "ikut_bpjs_ketenagakerjaan", 1)
            ),
        }

        # Cache employee data
        cache_value(cache_key, employee_data, CACHE_MEDIUM)

    return employee_data


@safe_execute(default_value={}, log_exception=True)
def get_ytd_totals(
    employee: str, 
    year: int, 
    month: int, 
    include_current: bool = False
) -> Dict[str, Any]:
    """
    Get YTD tax and other totals for an employee with caching.
    This centralized function provides consistent YTD data across the module.

    Args:
        employee: Employee ID
        year: Tax year
        month: Current month (1-12)
        include_current: Whether to include current month

    Returns:
        dict: Dictionary with ytd_gross, ytd_tax, ytd_bpjs, etc.
    """
    # Validate inputs
    if not employee or not year or not month:
        return {
            "ytd_gross": 0,
            "ytd_tax": 0,
            "ytd_bpjs": 0,
            "ytd_biaya_jabatan": 0,
            "ytd_netto": 0,
        }

    # Create cache key - include current month flag
    current_flag = "with_current" if include_current else "without_current"
    cache_key = f"ytd:{employee}:{year}:{month}:{current_flag}"

    # Check cache first
    cached_result = get_cached_value(cache_key)

    if cached_result is not None:
        return cached_result

    # First try to get from tax summary
    from_summary = get_ytd_totals_from_tax_summary(employee, year, month, include_current)

    # If summary had data, use it
    if from_summary and from_summary.get("has_data", False):
        # Cache result
        cache_value(cache_key, from_summary, CACHE_MEDIUM)
        return from_summary

    # If summary didn't have data or was incomplete, calculate from salary slips
    result = calculate_ytd_from_salary_slips(employee, year, month, include_current)

    # Cache result
    cache_value(cache_key, result, CACHE_MEDIUM)
    return result


@safe_execute(default_value={"has_data": False}, log_exception=True)
def get_ytd_totals_from_tax_summary(
    employee: str, 
    year: int, 
    month: int, 
    include_current: bool = False
) -> Dict[str, Any]:
    """
    Get YTD tax totals from Employee Tax Summary with efficient caching.

    Args:
        employee: Employee ID
        year: Tax year
        month: Current month (1-12)
        include_current: Whether to include current month

    Returns:
        dict: Dictionary with YTD totals and summary data
    """
    # Find Employee Tax Summary for this year
    tax_summary = frappe.db.get_value(
        "Employee Tax Summary",
        {"employee": employee, "year": year},
        ["name", "ytd_tax"],
        as_dict=1,
    )

    if not tax_summary:
        return {"has_data": False}

    # Prepare filter for monthly details
    month_filter = ["<=", month] if include_current else ["<", month]

    # Efficient query to get monthly details with all fields at once
    monthly_details = frappe.get_all(
        "Employee Tax Summary Detail",
        filters={"parent": tax_summary.name, "month": month_filter},
        fields=[
            "gross_pay",
            "bpjs_deductions",
            "tax_amount",
            "month",
            "is_using_ter",
            "ter_rate",
        ],
    )

    if not monthly_details:
        return {"has_data": False}

    # Calculate YTD totals
    ytd_gross = sum(flt(d.gross_pay) for d in monthly_details)
    ytd_bpjs = sum(flt(d.bpjs_deductions) for d in monthly_details)
    ytd_tax = sum(
        flt(d.tax_amount) for d in monthly_details
    )  # Use sum instead of tax_summary.ytd_tax to ensure consistency

    # Estimate biaya_jabatan if not directly available
    ytd_biaya_jabatan = 0
    for detail in monthly_details:
        # Rough estimate using standard formula - this should be improved if possible
        if flt(detail.gross_pay) > 0:
            # Use constants for calculation
            monthly_biaya_jabatan = min(
                flt(detail.gross_pay) * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX
            )
            ytd_biaya_jabatan += monthly_biaya_jabatan

    # Calculate netto
    ytd_netto = ytd_gross - ytd_bpjs - ytd_biaya_jabatan

    # Extract latest TER information
    is_using_ter = False
    highest_ter_rate = 0

    for detail in monthly_details:
        if detail.is_using_ter:
            is_using_ter = True
            if flt(detail.ter_rate) > highest_ter_rate:
                highest_ter_rate = flt(detail.ter_rate)

    result = {
        "has_data": True,
        "ytd_gross": ytd_gross,
        "ytd_tax": ytd_tax,
        "ytd_bpjs": ytd_bpjs,
        "ytd_biaya_jabatan": ytd_biaya_jabatan,
        "ytd_netto": ytd_netto,
        "is_using_ter": is_using_ter,
        "ter_rate": highest_ter_rate,
        "source": "tax_summary",
        "summary_name": tax_summary.name,
    }

    return result


@safe_execute(default_value={}, log_exception=True)
def calculate_ytd_from_salary_slips(
    employee: str, 
    year: int, 
    month: int, 
    include_current: bool = False
) -> Dict[str, Any]:
    """
    Calculate YTD totals from salary slips with caching.

    Args:
        employee: Employee ID
        year: Tax year
        month: Current month (1-12)
        include_current: Whether to include current month

    Returns:
        dict: Dictionary with ytd_gross, ytd_tax, ytd_bpjs, etc.
    """
    # Calculate date range
    start_date = f"{year}-01-01"

    if include_current:
        end_date = f"{year}-{month:02d}-31"  # Use end of month
    else:
        # Use end of previous month
        if month > 1:
            end_date = f"{year}-{(month - 1):02d}-31"
        else:
            # If month is January and not including current, return zeros
            return {
                "has_data": True,
                "ytd_gross": 0,
                "ytd_tax": 0,
                "ytd_bpjs": 0,
                "ytd_biaya_jabatan": 0,
                "ytd_netto": 0,
                "is_using_ter": False,
                "ter_rate": 0,
                "source": "salary_slips",
            }

    # Get salary slips within date range using parameterized query
    slips_query = """
        SELECT name, gross_pay, is_using_ter, ter_rate, biaya_jabatan, posting_date
        FROM `tabSalary Slip`
        WHERE employee = %s
        AND start_date >= %s
        AND end_date <= %s
        AND docstatus = 1
    """

    slips = frappe.db.sql(slips_query, [employee, start_date, end_date], as_dict=1)

    if not slips:
        return {
            "has_data": True,
            "ytd_gross": 0,
            "ytd_tax": 0,
            "ytd_bpjs": 0,
            "ytd_biaya_jabatan": 0,
            "ytd_netto": 0,
            "is_using_ter": False,
            "ter_rate": 0,
            "source": "salary_slips",
        }

    # Prepare for efficient batch query of all components
    slip_names = [slip.name for slip in slips]

    # Get all components at once
    components_query = """
        SELECT sd.parent, sd.salary_component, sd.amount
        FROM `tabSalary Detail` sd
        WHERE sd.parent IN %s
        AND sd.parentfield = 'deductions'
        AND sd.salary_component IN ('PPh 21', 'BPJS JHT Employee', 'BPJS JP Employee', 'BPJS Kesehatan Employee')
    """

    components = frappe.db.sql(components_query, [tuple(slip_names)], as_dict=1)

    # Organize components by slip
    slip_components = {}
    for comp in components:
        if comp.parent not in slip_components:
            slip_components[comp.parent] = []
        slip_components[comp.parent].append(comp)

    # Calculate totals
    ytd_gross = 0
    ytd_tax = 0
    ytd_bpjs = 0
    ytd_biaya_jabatan = 0
    is_using_ter = False
    highest_ter_rate = 0

    for slip in slips:
        ytd_gross += flt(slip.gross_pay)
        ytd_biaya_jabatan += flt(getattr(slip, "biaya_jabatan", 0))

        # Check TER info
        if getattr(slip, "is_using_ter", 0):
            is_using_ter = True
            if flt(getattr(slip, "ter_rate", 0)) > highest_ter_rate:
                highest_ter_rate = flt(getattr(slip, "ter_rate", 0))

        # Process components for this slip
        slip_comps = slip_components.get(slip.name, [])
        for comp in slip_comps:
            if comp.salary_component == "PPh 21":
                ytd_tax += flt(comp.amount)
            elif comp.salary_component in [
                "BPJS JHT Employee",
                "BPJS JP Employee",
                "BPJS Kesehatan Employee",
            ]:
                ytd_bpjs += flt(comp.amount)

    # If biaya_jabatan wasn't in slips, estimate it
    if ytd_biaya_jabatan == 0 and ytd_gross > 0:
        # Apply standard formula per month
        months_processed = len(
            {
                getdate(slip.posting_date).month
                for slip in slips
                if hasattr(slip, "posting_date")
            }
        )
        months_processed = max(1, months_processed)  # Ensure at least 1 month

        # Use constants for calculation
        ytd_biaya_jabatan = min(
            ytd_gross * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX * months_processed
        )

    # Calculate netto
    ytd_netto = ytd_gross - ytd_bpjs - ytd_biaya_jabatan

    result = {
        "has_data": True,
        "ytd_gross": ytd_gross,
        "ytd_tax": ytd_tax,
        "ytd_bpjs": ytd_bpjs,
        "ytd_biaya_jabatan": ytd_biaya_jabatan,
        "ytd_netto": ytd_netto,
        "is_using_ter": is_using_ter,
        "ter_rate": highest_ter_rate,
        "source": "salary_slips",
    }

    return result


@safe_execute(default_value={"ytd_tax": 0, "is_using_ter": 0, "ter_rate": 0}, log_exception=True)
def get_ytd_tax_info(employee, date=None, is_december_override=False):
    """
    Get year-to-date tax information for an employee.
    Uses the centralized get_ytd_totals function.

    Args:
        employee (str): Employee ID
        date (datetime, optional): Date to determine year and month, defaults to current date
        is_december_override (bool, optional): Flag to override December behavior

    Returns:
        dict: YTD tax information
    """
    # Validate employee parameter
    if not employee:
        frappe.throw(_("Employee is required to get YTD tax information"))

    # Check if employee exists
    ensure_doc_exists("Employee", employee)

    # Determine tax year and month from date
    if not date:
        date = getdate()

    year = date.year
    month = date.month

    # Get YTD totals using the centralized function
    ytd_data = get_ytd_totals(employee, year, month)

    # Return simplified result for backward compatibility
    return {
        "ytd_tax": flt(ytd_data.get("ytd_tax", 0)),
        "is_using_ter": ytd_data.get("is_using_ter", False)
        and not is_december_run(is_december_override),
        "ter_rate": flt(ytd_data.get("ter_rate", 0)),
    }


@safe_execute(default_value=None, log_exception=True)
def create_tax_summary_doc(
    employee, 
    year, 
    tax_amount=0, 
    is_using_ter=0, 
    ter_rate=0
):
    """
    Create or update Employee Tax Summary document.

    Args:
        employee (str): Employee ID
        year (int): Tax year
        tax_amount (float): PPh 21 amount to add
        is_using_ter (int): Whether TER method is used
        ter_rate (float): TER rate if applicable

    Returns:
        object: Employee Tax Summary document or None on error
    """
    # Validate required parameters
    if not employee:
        frappe.throw(_("Employee is required to create tax summary"))

    if not year or not isinstance(year, int):
        frappe.throw(_("Valid tax year is required to create tax summary"))

    # Convert numeric parameters
    tax_amount = flt(tax_amount)
    is_using_ter = cint(is_using_ter)
    ter_rate = flt(ter_rate)

    # Check if DocType exists
    ensure_doc_exists("DocType", "Employee Tax Summary")

    # Check if employee exists
    ensure_doc_exists("Employee", employee)

    # Check if tax summary exists for this employee and year
    name = frappe.db.get_value("Employee Tax Summary", {"employee": employee, "year": year})

    if name:
        # Update existing document
        doc = frappe.get_doc("Employee Tax Summary", name)

        # Update values
        doc.ytd_tax = flt(doc.ytd_tax) + tax_amount

        if is_using_ter:
            doc.is_using_ter = 1
            doc.ter_rate = max(doc.ter_rate or 0, ter_rate)

        # Save with flags to bypass validation
        doc.flags.ignore_validate_update_after_submit = True
        doc.save(ignore_permissions=True)

        return doc
    else:
        # Create new document
        employee_name = frappe.db.get_value("Employee", employee, "employee_name") or employee

        doc = frappe.new_doc("Employee Tax Summary")
        doc.employee = employee
        doc.employee_name = employee_name
        doc.year = year
        doc.ytd_tax = tax_amount

        # Set TER info if applicable
        if is_using_ter:
            doc.is_using_ter = 1
            doc.ter_rate = ter_rate

        # Set title if field exists
        if hasattr(doc, "title"):
            doc.title = f"{employee_name} - {year}"

        # Insert with flags to bypass validation
        doc.insert(ignore_permissions=True)
