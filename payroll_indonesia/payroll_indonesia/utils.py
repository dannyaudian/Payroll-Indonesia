# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-17 06:09:33 by dannyaudian

import frappe
import json
import os
from pathlib import Path
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime
from typing import Dict, Any, Optional, List

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

# Define exports
__all__ = [
    "debug_log",
    "get_settings",
    "get_default_config",
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

# Settings cache
settings_cache = {}
config_cache = {}
parent_account_cache = {}
cache_expiry = {}
CACHE_EXPIRY_SECONDS = 3600  # 1 hour


def debug_log(message: str, context: str = "GL Setup", max_length: int = 500, trace: bool = False):
    """
    Debug logging helper with consistent format for tracing and contextual information

    Args:
        message: Message to log
        context: Context identifier for the log
        max_length: Maximum message length to avoid memory issues
        trace: Whether to include traceback
    """
    timestamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    logger = frappe.logger("payroll_indonesia")

    # Always truncate for safety
    message = str(message)[:max_length]

    # Format with context
    log_message = f"[{timestamp}] [{context}] {message}"

    # Log at appropriate level
    logger.info(log_message)

    if trace:
        logger.info(f"[{timestamp}] [{context}] [TRACE] {frappe.get_traceback()[:max_length]}")


def get_settings():
    """Get Payroll Indonesia Settings, create if doesn't exist"""
    try:
        # Try to get settings from cache first
        cache_key = "payroll_indonesia_settings"
        if cache_key in settings_cache:
            # Check if cache is still valid
            if cache_expiry.get(cache_key, 0) > frappe.utils.now_datetime().timestamp():
                return settings_cache[cache_key]

        # Get settings from database
        if not frappe.db.exists("Payroll Indonesia Settings", "Payroll Indonesia Settings"):
            # Create settings with defaults (fallback)
            settings = create_default_settings()
        else:
            settings = frappe.get_doc("Payroll Indonesia Settings", "Payroll Indonesia Settings")

        # Cache the settings
        settings_cache[cache_key] = settings
        cache_expiry[cache_key] = frappe.utils.now_datetime().timestamp() + CACHE_EXPIRY_SECONDS

        return settings
    except Exception as e:
        frappe.log_error(f"Error getting Payroll Indonesia Settings: {str(e)}", "Settings Error")
        # If settings can't be loaded, return an empty doc as fallback
        return frappe.get_doc({"doctype": "Payroll Indonesia Settings"})


def get_default_config(section: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns configuration values from defaults.json with caching.

    This function is the single source of truth for default configurations
    across the entire Payroll Indonesia module.

    Args:
        section: Specific configuration section to return.
                If None, returns the entire config.

    Returns:
        dict: Configuration settings or specific section
    """
    # Check if config is in cache
    cache_key = f"default_config:{section or 'all'}"
    if cache_key in config_cache:
        # Check if cache is still valid
        if cache_expiry.get(cache_key, 0) > frappe.utils.now_datetime().timestamp():
            return config_cache[cache_key]

    # Get defaults from JSON file first
    defaults_from_file = _load_defaults_json()

    # Get settings document for overrides
    settings = get_settings()

    # Build config dictionary from both sources with settings taking precedence
    config = {
        "bpjs_kesehatan": {
            "employee_contribution": getattr(
                settings,
                "kesehatan_employee_percent",
                defaults_from_file.get("kesehatan_employee_percent", 1.0),
            ),
            "employer_contribution": getattr(
                settings,
                "kesehatan_employer_percent",
                defaults_from_file.get("kesehatan_employer_percent", 4.0),
            ),
            "max_salary": getattr(
                settings,
                "kesehatan_max_salary",
                defaults_from_file.get("kesehatan_max_salary", 12000000.0),
            ),
        },
        "bpjs_ketenagakerjaan": {
            "jht": {
                "employee_contribution": getattr(
                    settings,
                    "jht_employee_percent",
                    defaults_from_file.get("jht_employee_percent", 2.0),
                ),
                "employer_contribution": getattr(
                    settings,
                    "jht_employer_percent",
                    defaults_from_file.get("jht_employer_percent", 3.7),
                ),
            },
            "jkk": {
                "employer_contribution": getattr(
                    settings, "jkk_percent", defaults_from_file.get("jkk_percent", 0.24)
                ),
            },
            "jkm": {
                "employer_contribution": getattr(
                    settings, "jkm_percent", defaults_from_file.get("jkm_percent", 0.3)
                ),
            },
            "jp": {
                "employee_contribution": getattr(
                    settings,
                    "jp_employee_percent",
                    defaults_from_file.get("jp_employee_percent", 1.0),
                ),
                "employer_contribution": getattr(
                    settings,
                    "jp_employer_percent",
                    defaults_from_file.get("jp_employer_percent", 2.0),
                ),
                "max_salary": getattr(
                    settings, "jp_max_salary", defaults_from_file.get("jp_max_salary", 9077600.0)
                ),
            },
        },
        "ptkp_values": (
            settings.get_ptkp_values_dict()
            if hasattr(settings, "get_ptkp_values_dict")
            else defaults_from_file.get("ptkp", {})
        ),
        "ptkp_to_ter_mapping": (
            settings.get_ptkp_ter_mapping_dict()
            if hasattr(settings, "get_ptkp_ter_mapping_dict")
            else defaults_from_file.get("ptkp_to_ter_mapping", {})
        ),
        "tax_brackets": (
            settings.get_tax_brackets_list()
            if hasattr(settings, "get_tax_brackets_list")
            else defaults_from_file.get("tax_brackets", [])
        ),
        "tipe_karyawan": (
            settings.get_tipe_karyawan_list()
            if hasattr(settings, "get_tipe_karyawan_list")
            else defaults_from_file.get("tipe_karyawan", [])
        ),
        "gl_accounts": defaults_from_file.get("gl_accounts", {}),
    }

    # Add account settings with fallbacks
    config["bpjs_payable_parent_account"] = getattr(
        settings, "bpjs_payable_parent_account", "Current Liabilities"
    )
    config["bpjs_expense_parent_account"] = getattr(
        settings, "bpjs_expense_parent_account", "Expenses"
    )

    # Add parent account candidates
    config["parent_account_candidates"] = {
        "Liability": _get_parent_account_candidates_liability(settings),
        "Expense": _get_parent_account_candidates_expense(settings),
        "Income": ["Income", "Direct Income", "Indirect Income"],
        "Asset": ["Current Assets", "Fixed Assets"],
    }

    # Cache the result
    config_cache[cache_key] = config if section is None else config.get(section, {})
    cache_expiry[cache_key] = frappe.utils.now_datetime().timestamp() + CACHE_EXPIRY_SECONDS

    # Return full config or just the requested section
    if section:
        return config.get(section, {})

    return config


def _get_parent_account_candidates_liability(settings) -> List[str]:
    """
    Get list of parent account candidates for liability accounts

    Args:
        settings: Payroll Indonesia Settings document

    Returns:
        List[str]: List of account names
    """
    if (
        hasattr(settings, "parent_account_candidates_liability")
        and settings.parent_account_candidates_liability
    ):
        candidates = settings.parent_account_candidates_liability.split("\n")
        return [candidate.strip() for candidate in candidates if candidate.strip()]

    # Default candidates
    return ["Duties and Taxes", "Current Liabilities", "Accounts Payable"]


def _get_parent_account_candidates_expense(settings) -> List[str]:
    """
    Get list of parent account candidates for expense accounts

    Args:
        settings: Payroll Indonesia Settings document

    Returns:
        List[str]: List of account names
    """
    if (
        hasattr(settings, "parent_account_candidates_expense")
        and settings.parent_account_candidates_expense
    ):
        candidates = settings.parent_account_candidates_expense.split("\n")
        return [candidate.strip() for candidate in candidates if candidate.strip()]

    # Default candidates
    return ["Direct Expenses", "Indirect Expenses", "Expenses"]


def create_default_settings():
    """Create default settings when not available"""
    settings = frappe.get_doc(
        {
            "doctype": "Payroll Indonesia Settings",
            "app_version": "1.0.0",
            "app_last_updated": frappe.utils.now(),
            "app_updated_by": "dannyaudian",
            # BPJS defaults
            "kesehatan_employee_percent": 1.0,
            "kesehatan_employer_percent": 4.0,
            "kesehatan_max_salary": 12000000.0,
            "jht_employee_percent": 2.0,
            "jht_employer_percent": 3.7,
            "jp_employee_percent": 1.0,
            "jp_employer_percent": 2.0,
            "jp_max_salary": 9077600.0,
            "jkk_percent": 0.24,
            "jkm_percent": 0.3,
            # Tax defaults
            "umr_default": 4900000.0,
            "biaya_jabatan_percent": 5.0,
            "biaya_jabatan_max": 500000.0,
            "tax_calculation_method": "TER",
            "use_ter": 1,
            # Default settings
            "default_currency": "IDR",
            "payroll_frequency": "Monthly",
            "max_working_days_per_month": 22,
            "working_hours_per_day": 8,
            # Salary structure
            "basic_salary_percent": 75,
            "meal_allowance": 750000.0,
            "transport_allowance": 900000.0,
            "position_allowance_percent": 7.5,
            # Parent account candidates
            "parent_account_candidates_liability": "Duties and Taxes\nCurrent Liabilities\nAccounts Payable",
            "parent_account_candidates_expense": "Direct Expenses\nIndirect Expenses\nExpenses",
        }
    )

    # Insert with permission bypass
    settings.flags.ignore_permissions = True
    settings.flags.ignore_mandatory = True
    settings.insert(ignore_permissions=True)

    frappe.db.commit()
    return settings


def _load_defaults_json() -> Dict[str, Any]:
    """
    Load defaults from the config/defaults.json file

    Returns:
        dict: Default configuration values
    """
    try:
        app_path = frappe.get_app_path("payroll_indonesia")
        defaults_file = Path(app_path) / "config" / "defaults.json"

        if defaults_file.exists():
            with open(defaults_file, "r") as f:
                return json.load(f)
        else:
            debug_log(f"defaults.json not found at {defaults_file}", "Configuration")
            return {}
    except Exception as e:
        debug_log(f"Error loading defaults.json: {str(e)}", "Configuration", trace=True)
        return {}


def find_parent_account(
    company: str,
    account_type: str,
    root_type: Optional[str] = None,
) -> Optional[str]:
    """
    Find appropriate parent account based on account type and root type.
    This is the centralized function for all parent account lookups.

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

    # Create cache key
    cache_key = f"parent_account:{company}:{account_type}:{root_type}"

    # Check cache first
    if cache_key in parent_account_cache:
        # Check if cache is still valid
        if cache_expiry.get(cache_key, 0) > now_datetime().timestamp():
            return parent_account_cache[cache_key]

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
                    f"Could not find any parent account for {account_type} (root_type: {root_type}) in company {company}",
                    "Account Lookup Error",
                )
                # Don't cache negative results
                return None

    # Cache the successful result
    parent_account_cache[cache_key] = parent_account
    cache_expiry[cache_key] = now_datetime().timestamp() + CACHE_EXPIRY_SECONDS

    return parent_account


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


def _get_root_type_from_account_type(account_type: str) -> str:
    """
    Determine the root type based on account type

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
    Get parent account candidates for the given root type

    Args:
        root_type: Root type of account

    Returns:
        List[str]: List of candidate account names
    """
    # Get from config
    config = get_default_config()
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


def _find_parent_from_candidates(company: str, candidates: List[str], abbr: str) -> Optional[str]:
    """
    Find parent account from the list of candidates

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
            "Account", {"account_name": candidate, "company": company, "is_group": 1}, "name"
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
    Find any group account with the correct root_type as fallback

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


def create_account(
    company: str,
    account_name: str,
    account_type: str,
    parent: Optional[str] = None,
    root_type: Optional[str] = None,
    is_group: int = 0,
) -> Optional[str]:
    """
    Create GL Account if not exists with standardized naming and enhanced validation

    This is the single source of truth for account creation in Payroll Indonesia.
    It handles all account creation logic, including finding appropriate parent accounts.

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

    try:
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

    except Exception as e:
        debug_log(
            f"Error creating account {account_name} for {company}: {str(e)}",
            "Account Error",
            trace=True,
        )
        return None


def create_parent_liability_account(company: str) -> Optional[str]:
    """
    Create or get parent liability account for BPJS accounts

    Uses the centralized create_account function with group account settings.

    Args:
        company: Company name

    Returns:
        str: Parent account name if created or already exists, None otherwise
    """
    try:
        # Validate company
        if not company:
            frappe.throw(_("Company is required to create parent liability account"))

        # Get settings for account name
        settings = get_settings()
        account_name = "BPJS Payable"  # Default

        # Check if settings has a GL account configuration
        if settings:
            # Try to get GL accounts data from settings
            gl_accounts_data = {}
            try:
                if hasattr(settings, "gl_accounts") and settings.gl_accounts:
                    if isinstance(settings.gl_accounts, str):
                        gl_accounts_data = json.loads(settings.gl_accounts)
                    else:
                        gl_accounts_data = settings.gl_accounts
            except (ValueError, AttributeError):
                debug_log("Error parsing GL accounts data from settings", "Account Creation")

            # Look for parent_accounts configuration
            if gl_accounts_data and "parent_accounts" in gl_accounts_data:
                parent_accounts = gl_accounts_data.get("parent_accounts", {})
                if "bpjs_payable" in parent_accounts:
                    account_name = parent_accounts.get("bpjs_payable", {}).get(
                        "account_name", account_name
                    )

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
                    frappe.log_error(
                        f"Could not convert {full_account_name} to group account: {str(e)}",
                        "Account Creation Error",
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

    except Exception as e:
        frappe.log_error(
            f"Error in create_parent_liability_account for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Account Creation Error",
        )
        return None


def create_parent_expense_account(company: str) -> Optional[str]:
    """
    Create or get parent expense account for BPJS accounts

    Uses the centralized create_account function with group account settings.

    Args:
        company: Company name

    Returns:
        str: Parent account name if created or already exists, None otherwise
    """
    try:
        # Validate company
        if not company:
            frappe.throw(_("Company is required to create parent expense account"))

        # Get settings for account name
        settings = get_settings()
        account_name = "BPJS Expenses"  # Default

        # Check if settings has a GL account configuration
        if settings:
            # Try to get GL accounts data from settings
            gl_accounts_data = {}
            try:
                if hasattr(settings, "gl_accounts") and settings.gl_accounts:
                    if isinstance(settings.gl_accounts, str):
                        gl_accounts_data = json.loads(settings.gl_accounts)
                    else:
                        gl_accounts_data = settings.gl_accounts
            except (ValueError, AttributeError):
                debug_log("Error parsing GL accounts data from settings", "Account Creation")

            # Look for parent_accounts configuration
            if gl_accounts_data and "parent_accounts" in gl_accounts_data:
                parent_accounts = gl_accounts_data.get("parent_accounts", {})
                if "bpjs_expenses" in parent_accounts:
                    account_name = parent_accounts.get("bpjs_expenses", {}).get(
                        "account_name", account_name
                    )

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
                    frappe.log_error(
                        f"Could not convert {full_account_name} to group account: {str(e)}",
                        "Account Creation Error",
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

    except Exception as e:
        frappe.log_error(
            f"Error in create_parent_expense_account for {company}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Account Creation Error",
        )
        return None


def retry_bpjs_mapping(companies: List[str]) -> None:
    """
    Background job to retry failed BPJS mapping creation
    Called via frappe.enqueue() from ensure_bpjs_mapping_for_all_companies

    Args:
        companies: List of company names to retry mapping for
    """
    if not companies:
        return

    try:
        # Import conditionally to avoid circular imports
        module_path = (
            "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping"
        )
        try:
            module = frappe.get_module(module_path)
            create_default_mapping = getattr(module, "create_default_mapping", None)
        except (ImportError, AttributeError) as e:
            frappe.log_error(
                f"Failed to import create_default_mapping: {str(e)}", "BPJS Mapping Error"
            )
            return

        if not create_default_mapping:
            frappe.log_error("create_default_mapping function not found", "BPJS Mapping Error")
            return

        # Get account mapping from Payroll Indonesia Settings
        settings = get_settings()

        # Get account mapping from settings
        account_mapping = {}
        if settings:
            # Try to get GL accounts data from settings
            gl_accounts_data = {}
            try:
                if hasattr(settings, "gl_accounts") and settings.gl_accounts:
                    if isinstance(settings.gl_accounts, str):
                        gl_accounts_data = json.loads(settings.gl_accounts)
                    else:
                        gl_accounts_data = settings.gl_accounts

                    if "bpjs_account_mapping" in gl_accounts_data:
                        account_mapping = gl_accounts_data["bpjs_account_mapping"]
            except (ValueError, AttributeError):
                debug_log("Error parsing GL accounts data from settings", "BPJS Mapping Retry")

        for company in companies:
            try:
                if not frappe.db.exists("BPJS Account Mapping", {"company": company}):
                    debug_log(
                        f"Retrying BPJS Account Mapping creation for {company}",
                        "BPJS Mapping Retry",
                    )
                    mapping_name = create_default_mapping(company, account_mapping)

                    if mapping_name:
                        frappe.logger().info(
                            f"Successfully created BPJS Account Mapping for {company} on retry"
                        )
                        debug_log(
                            f"Successfully created BPJS Account Mapping for {company} on retry",
                            "BPJS Mapping Retry",
                        )
                    else:
                        frappe.logger().warning(
                            f"Failed again to create BPJS Account Mapping for {company}"
                        )
                        debug_log(
                            f"Failed again to create BPJS Account Mapping for {company}",
                            "BPJS Mapping Retry Error",
                        )
            except Exception as e:
                frappe.log_error(
                    f"Error creating BPJS Account Mapping for {company} on retry: {str(e)}\n\n"
                    f"Traceback: {frappe.get_traceback()}",
                    "BPJS Mapping Retry Error",
                )
                debug_log(
                    f"Error in retry for company {company}: {str(e)}",
                    "BPJS Mapping Retry Error",
                    trace=True,
                )

    except Exception as e:
        frappe.log_error(
            f"Error in retry_bpjs_mapping: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "BPJS Mapping Retry Error",
        )


# BPJS Settings and Calculation Functions
@memoize_with_ttl(ttl=CACHE_MEDIUM)
def get_bpjs_settings() -> Dict[str, Any]:
    """
    Get BPJS settings from Payroll Indonesia Settings with caching

    Returns:
        dict: Dictionary containing structured BPJS settings
    """
    # Default settings to use if DocType doesn't exist
    defaults = {
        "kesehatan": {"employee_percent": 1.0, "employer_percent": 4.0, "max_salary": 12000000},
        "jht": {"employee_percent": 2.0, "employer_percent": 3.7},
        "jp": {"employee_percent": 1.0, "employer_percent": 2.0, "max_salary": 9077600},
        "jkk": {"percent": 0.24},
        "jkm": {"percent": 0.3},
    }

    # Get settings from Payroll Indonesia Settings
    settings_doc = get_settings()

    if not settings_doc:
        return defaults

    # Convert to structured format
    return {
        "kesehatan": {
            "employee_percent": flt(getattr(settings_doc, "kesehatan_employee_percent", 1.0)),
            "employer_percent": flt(getattr(settings_doc, "kesehatan_employer_percent", 4.0)),
            "max_salary": flt(getattr(settings_doc, "kesehatan_max_salary", 12000000)),
        },
        "jht": {
            "employee_percent": flt(getattr(settings_doc, "jht_employee_percent", 2.0)),
            "employer_percent": flt(getattr(settings_doc, "jht_employer_percent", 3.7)),
        },
        "jp": {
            "employee_percent": flt(getattr(settings_doc, "jp_employee_percent", 1.0)),
            "employer_percent": flt(getattr(settings_doc, "jp_employer_percent", 2.0)),
            "max_salary": flt(getattr(settings_doc, "jp_max_salary", 9077600)),
        },
        "jkk": {"percent": flt(getattr(settings_doc, "jkk_percent", 0.24))},
        "jkm": {"percent": flt(getattr(settings_doc, "jkm_percent", 0.3))},
    }


def calculate_bpjs_contributions(salary, bpjs_settings=None):
    """
    Calculate BPJS contributions based on salary and settings
    with improved validation and error handling

    Args:
        salary (float): Base salary amount
        bpjs_settings (object, optional): BPJS Settings or dict. Will fetch if not provided.

    Returns:
        dict: Dictionary containing BPJS contribution details
    """
    try:
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
    except Exception as e:
        frappe.log_error(
            f"Error calculating BPJS contributions: {str(e)}", "BPJS Calculation Error"
        )
        debug_log(
            f"Error calculating BPJS contributions: {str(e)}", "Calculation Error", trace=True
        )

        # Return empty structure to avoid breaking code that relies on the structure
        return {
            "kesehatan": {"karyawan": 0, "perusahaan": 0, "total": 0},
            "ketenagakerjaan": {
                "jht": {"karyawan": 0, "perusahaan": 0, "total": 0},
                "jp": {"karyawan": 0, "perusahaan": 0, "total": 0},
                "jkk": 0,
                "jkm": 0,
            },
        }


# PPh 21 Settings functions
@memoize_with_ttl(ttl=CACHE_MEDIUM)
def get_pph21_settings() -> Dict[str, Any]:
    """
    Get PPh 21 settings from Payroll Indonesia Settings with caching

    Returns:
        dict: PPh 21 settings including calculation method and TER usage
    """
    # Default settings if DocType not found
    defaults = {
        "calculation_method": "Progressive",
        "use_ter": 0,
        "ptkp_settings": get_ptkp_settings(),
        "brackets": get_pph21_brackets(),
    }

    # Get settings from Payroll Indonesia Settings
    settings_doc = get_settings()

    if not settings_doc:
        return defaults

    # Extract relevant fields
    calculation_method = getattr(settings_doc, "tax_calculation_method", "Progressive")
    use_ter = cint(getattr(settings_doc, "use_ter", 0))

    return {
        "calculation_method": calculation_method,
        "use_ter": use_ter,
        "ptkp_settings": get_ptkp_settings(),
        "brackets": get_pph21_brackets(),
    }


@memoize_with_ttl(ttl=CACHE_LONG)  # PTKP values rarely change
def get_ptkp_settings() -> Dict[str, float]:
    """
    Get PTKP settings from Payroll Indonesia Settings with caching

    Returns:
        dict: Dictionary mapping tax status codes to PTKP values
    """
    # Default PTKP values
    defaults = {
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

    try:
        # Get settings from Payroll Indonesia Settings
        settings = get_settings()

        if not settings:
            return defaults

        # Check if settings has ptkp_table
        if hasattr(settings, "ptkp_table") and settings.ptkp_table:
            result = {}
            # Get PTKP values from child table
            for row in settings.ptkp_table:
                if hasattr(row, "status_pajak") and hasattr(row, "ptkp_amount"):
                    result[row.status_pajak] = float(row.ptkp_amount)

            if result:
                # Cache for 24 hours
                frappe.cache().set_value("ptkp_settings", result, expires_in_sec=CACHE_LONG)
                return result
    except Exception as e:
        frappe.log_error(
            f"Error retrieving PTKP settings from Payroll Indonesia Settings: {str(e)}",
            "PTKP Settings Error",
        )

    # Cache default values for 1 hour
    frappe.cache().set_value("ptkp_settings", defaults, expires_in_sec=CACHE_MEDIUM)
    return defaults


@memoize_with_ttl(ttl=CACHE_LONG)  # Tax brackets rarely change
def get_pph21_brackets() -> List[Dict[str, Any]]:
    """
    Get PPh 21 tax brackets from Payroll Indonesia Settings with caching

    Returns:
        list: List of tax brackets with income ranges and rates
    """
    # Default brackets based on current regulations
    defaults = [
        {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
        {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
        {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
        {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
        {"income_from": 5000000000, "income_to": 0, "tax_rate": 35},
    ]

    try:
        # Get settings from Payroll Indonesia Settings
        settings = get_settings()

        if not settings:
            return defaults

        # Check if settings has tax_brackets_table
        if hasattr(settings, "tax_brackets_table") and settings.tax_brackets_table:
            brackets = []
            # Process brackets from child table
            for row in settings.tax_brackets_table:
                if (
                    hasattr(row, "income_from")
                    and hasattr(row, "income_to")
                    and hasattr(row, "tax_rate")
                ):
                    brackets.append(
                        {
                            "income_from": flt(row.income_from),
                            "income_to": flt(row.income_to),
                            "tax_rate": flt(row.tax_rate),
                        }
                    )

            if brackets:
                # Sort by income_from
                brackets.sort(key=lambda x: x["income_from"])

                # Cache for 24 hours
                frappe.cache().set_value("pph21_brackets", brackets, expires_in_sec=CACHE_LONG)
                return brackets
    except Exception as e:
        frappe.log_error(
            f"Error retrieving PPh 21 brackets from Payroll Indonesia Settings: {str(e)}",
            "PPh 21 Brackets Error",
        )

    # Cache default values for 1 hour
    frappe.cache().set_value("pph21_brackets", defaults, expires_in_sec=CACHE_MEDIUM)
    return defaults


def get_spt_month() -> int:
    """
    Get the month for annual SPT calculation

    Returns:
        int: Month number (1-12)
    """
    try:
        # Try to get from Payroll Indonesia Settings
        settings = get_settings()
        spt_month = getattr(settings, "spt_month", None)

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
    except Exception as e:
        frappe.log_error(f"Error getting SPT month: {str(e)}", "SPT Month Error")
        return 12  # Default to December


# Helper function to determine if December run
def is_december_run(flag: int) -> bool:
    """
    Determine if this is a December run based on flag

    Args:
        flag: is_december_override flag (0 or 1)

    Returns:
        bool: True if December run, False otherwise
    """
    return bool(flag)


# TER-related functions
def get_ter_category(ptkp_status):
    """
    Map PTKP status to TER category using Payroll Indonesia Settings

    Args:
        ptkp_status (str): Tax status code (e.g., 'TK0', 'K1')

    Returns:
        str: Corresponding TER category
    """
    try:
        # Get mapping from Payroll Indonesia Settings
        settings = get_settings()

        # Check if settings has ptkp_ter_mapping_table
        if hasattr(settings, "ptkp_ter_mapping_table") and settings.ptkp_ter_mapping_table:
            # Look for the mapping in the child table
            for row in settings.ptkp_ter_mapping_table:
                if row.ptkp_status == ptkp_status:
                    return row.ter_category

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
    except Exception as e:
        frappe.log_error(f"Error mapping PTKP to TER: {str(e)}", "PTKP-TER Mapping Error")
        return TER_CATEGORY_C  # Default to highest category on error


def get_ter_rate(status_pajak, penghasilan_bruto):
    """
    Get TER rate for a specific tax status and income level

    Args:
        status_pajak (str): Tax status (TK0, K0, etc)
        penghasilan_bruto (float): Gross income

    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    try:
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
        cache_key = (
            f"ter_rate:{ter_category}:{int(penghasilan_bruto/1000)*1000}"  # Round to nearest 1000
        )
        cached_rate = frappe.cache().get_value(cache_key)

        if cached_rate is not None:
            return cached_rate

        # Try getting rate from settings
        settings = get_settings()
        if settings:
            # Check if settings has a method to get TER rate
            if hasattr(settings, "get_ter_rate") and callable(settings.get_ter_rate):
                try:
                    rate = settings.get_ter_rate(ter_category, penghasilan_bruto)
                    if rate is not None:
                        # Convert to decimal
                        decimal_rate = flt(rate) / 100.0
                        frappe.cache().set_value(
                            cache_key, decimal_rate, expires_in_sec=CACHE_MEDIUM
                        )
                        return decimal_rate
                except Exception as e:
                    frappe.log_error(
                        f"Error getting TER rate from settings: {str(e)}", "TER Rate Error"
                    )

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

    except Exception as e:
        frappe.log_error(
            f"Error getting TER rate for status {status_pajak} and income {penghasilan_bruto}: {str(e)}",
            "TER Rate Error",
        )
        return 0


def should_use_ter(salary_slip=None, is_december_override=False):
    """
    Check if TER method should be used based on Payroll Indonesia Settings
    and December override flag

    Args:
        salary_slip: Salary slip document (optional)
        is_december_override: Flag indicating if this is a December run (default: False)

    Returns:
        bool: True if TER should be used, False otherwise
    """
    try:
        # Get settings from Payroll Indonesia Settings
        settings = get_settings()

        if not settings:
            return False

        calc_method = getattr(settings, "tax_calculation_method", "Progressive")
        use_ter = cint(getattr(settings, "use_ter", 0))

        # Check if this is a December run
        if salary_slip and hasattr(salary_slip, "is_december_override"):
            is_december_override = cint(salary_slip.is_december_override)

        # December always uses Progressive method as per PMK 168/2023
        if is_december_run(is_december_override):
            return False

        # Check settings
        return calc_method == "TER" and use_ter
    except Exception as e:
        frappe.log_error(f"Error checking TER method settings: {str(e)}", "TER Settings Error")
        return False


# YTD Functions - Consolidated for easier testing and reuse
def get_employee_details(employee_id=None, salary_slip=None):
    """
    Get employee details from either employee ID or salary slip
    with efficient caching

    Args:
        employee_id (str, optional): Employee ID
        salary_slip (str, optional): Salary slip name to extract employee ID from

    Returns:
        dict: Employee details
    """
    try:
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

        # Now we should have employee_id, get employee details from cache or DB
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

    except Exception as e:
        frappe.log_error(
            "Error retrieving employee details for {0} or slip {1}: {2}".format(
                employee_id or "unknown", salary_slip or "unknown", str(e)
            ),
            "Employee
