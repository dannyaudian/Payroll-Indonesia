# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 13:19:43 by dannyaudian

import frappe
import logging

# FIXED: Use correct import path for get_default_config
from payroll_indonesia.config.config import get_config as get_default_config, get_component_tax_effect
from payroll_indonesia.payroll_indonesia.utils import debug_log

# Setup logger
logger = logging.getLogger(__name__)


def map_gl_account(company: str, account_key: str, category: str) -> str:
    """
    Maps a base account key to a company-specific GL account.
    Note: This will NOT map BPJS accounts, which are now handled by BPJSAccountMapping DocType.

    Args:
        company (str): The company name for which to create the account mapping
        account_key (str): The key of the base account in defaults.json
        category (str): The category of the account (e.g., 'expense_accounts', 'payable_accounts')

    Returns:
        str: The mapped account name with company suffix
    """
    try:
        # Skip BPJS account mapping - handled by BPJSAccountMapping DocType
        if "bpjs" in account_key.lower() or category.startswith("bpjs_"):
            debug_log(
                f"Skipping BPJS account mapping for {account_key} as it's handled by BPJSAccountMapping DocType",
                "GL Account Mapping",
            )
            return ""

        # Load configuration using centralized get_default_config helper
        config = get_default_config()

        if not config:
            logger.warning("Could not load defaults.json configuration")
            debug_log(
                f"Could not load defaults.json configuration when mapping {account_key}",
                "GL Account Mapping",
            )
            # Return fallback format using account_key as name
            return f"{account_key} - {company}"

        # Check if gl_accounts exists in config
        gl_accounts = config.get("gl_accounts", {})
        if not gl_accounts:
            logger.warning("No gl_accounts found in configuration")
            debug_log("No gl_accounts found in configuration", "GL Account Mapping")
            return f"{account_key} - {company}"

        # Check if category exists in gl_accounts
        if category not in gl_accounts:
            logger.warning(f"Category '{category}' not found in gl_accounts configuration")
            debug_log(
                f"Category '{category}' not found in gl_accounts configuration",
                "GL Account Mapping",
            )
            return f"{account_key} - {company}"

        # Get the category accounts
        category_accounts = gl_accounts[category]

        # Check if account_key exists in the category
        if account_key not in category_accounts:
            logger.warning(f"Account key '{account_key}' not found in '{category}' category")
            debug_log(
                f"Account key '{account_key}' not found in '{category}' category",
                "GL Account Mapping",
            )
            return f"{account_key} - {company}"

        # Get the account name from the config
        account_info = category_accounts[account_key]

        # Check if account_name exists in the account info
        if not isinstance(account_info, dict) or "account_name" not in account_info:
            logger.warning(f"Invalid account info or missing account_name for {account_key}")
            debug_log(
                f"Invalid account info or missing account_name for {account_key}",
                "GL Account Mapping",
            )
            return f"{account_key} - {company}"

        account_name = account_info["account_name"]

        # Get company abbreviation
        company_abbr = frappe.get_cached_value("Company", company, "abbr")

        # Return the formatted account name with company abbreviation
        formatted_account_name = f"{account_name} - {company_abbr}"

        # Check if account exists, create if needed
        if not frappe.db.exists("Account", formatted_account_name):
            # Get account type and root type from config
            account_type = account_info.get("account_type", "Expense")
            root_type = account_info.get("root_type", "Expense")

            # Determine default parent
            default_parent = "Expenses - " + company_abbr
            if root_type == "Liability":
                default_parent = "Liabilities - " + company_abbr
            elif root_type == "Asset":
                default_parent = "Assets - " + company_abbr

            # Create the account using base name (without suffix)
            get_or_create_account(
                company, account_name, account_type, root_type, default_parent
            )

        return formatted_account_name

    except Exception as e:
        logger.exception(f"Error mapping GL account for {account_key} in {category}: {str(e)}")
        debug_log(
            f"Error mapping GL account for {account_key} in {category}: {str(e)}",
            "GL Account Mapping Error",
        )
        # Return fallback format using account_key as name
        return f"{account_key} - {company}"


def get_gl_account_for_salary_component(company: str, salary_component: str) -> str:
    """
    Maps a salary component to its corresponding GL account for a specific company.
    Note: BPJS components now use accounts from BPJSAccountMapping DocType.

    Args:
        company (str): The company name
        salary_component (str): The name of the salary component

    Returns:
        str: The mapped GL account with company suffix
    """
    # Skip BPJS components - handled by BPJSAccountMapping DocType
    if "BPJS" in salary_component:
        debug_log(
            f"Skipping GL account mapping for BPJS component '{salary_component}' as it's handled by BPJSAccountMapping DocType",
            "Salary Component Mapping",
        )
        return ""

    # Define the mapping from salary component to account key and category
    component_mapping = {
        # Earnings
        "Gaji Pokok": ("beban_gaji_pokok", "expense_accounts"),
        "Tunjangan Makan": ("beban_tunjangan_makan", "expense_accounts"),
        "Tunjangan Transport": ("beban_tunjangan_transport", "expense_accounts"),
        "Insentif": ("beban_insentif", "expense_accounts"),
        "Bonus": ("beban_bonus", "expense_accounts"),
        # Deductions
        "PPh 21": ("hutang_pph21", "payable_accounts"),
    }

    # Get the component type (Earning or Deduction) to determine account category
    component_doc = None
    try:
        component_doc = frappe.get_doc("Salary Component", salary_component)
    except Exception as e:
        logger.warning(f"Could not load salary component {salary_component}: {str(e)}")
        
    component_type = "Earning"  # Default
    if component_doc and hasattr(component_doc, "type"):
        component_type = component_doc.type
    
    # Get tax effect for the component
    tax_effect = get_component_tax_effect(salary_component, component_type)
    
    # For components not in the explicit mapping, generate and create the account
    if salary_component not in component_mapping:
        # Map tax effect to base account name
        if tax_effect == "Penambah Bruto/Objek Pajak":
            base_name = f"Beban {salary_component}"
        elif tax_effect == "Pengurang Netto/Tax Deduction":
            base_name = f"Beban {salary_component}"
        elif tax_effect == "Natura/Fasilitas (Objek Pajak)":
            base_name = f"Beban Natura {salary_component}"
        elif tax_effect == "Natura/Fasilitas (Non-Objek Pajak)":
            base_name = f"Beban Fasilitas {salary_component}"
        else:  # Tidak Berpengaruh ke Pajak
            base_name = f"{salary_component} Account"

        # Create account if needed and return suffixed name
        return get_or_create_account(
            company, base_name, "Expense", "Expense"
        )
    
    # Get the account key and category from the mapping
    account_key, category = component_mapping[salary_component]

    # Return the mapped GL account
    return map_gl_account(company, account_key, category)


def get_or_create_account(
    company, account_name, account_type, root_type="Expense", parent_account=None
):
    """
    Get an existing account or create it if it doesn't exist.

    Args:
        company (str): Company name
        account_name (str): Base account name without company suffix
        account_type (str): Account type (e.g., 'Expense', 'Payable')
        root_type (str): Root type (e.g., 'Expense', 'Liability', 'Asset')
        parent_account (str, optional): Parent account name. If not provided, will try to find appropriate parent.

    Returns:
        str: Full account name with company suffix
    """
    try:
        # Get company abbreviation
        company_abbr = frappe.get_cached_value("Company", company, "abbr")

        full_account_name = f"{account_name} - {company_abbr}"

        # Check if account already exists
        if frappe.db.exists("Account", full_account_name):
            return full_account_name

        # Find appropriate parent account if not provided
        if not parent_account:
            if root_type == "Liability":
                parent_account = find_parent_account(company, "Payable", "Liability")
            elif root_type == "Asset":
                parent_account = find_parent_account(company, "Asset", "Asset")
            else:  # Expense
                parent_account = find_parent_account(company, "Expense", "Expense")

        if not parent_account:
            # Fallback to standard parent accounts
            if root_type == "Liability":
                parent_account = f"Liabilities - {company_abbr}"
            elif root_type == "Asset":
                parent_account = f"Assets - {company_abbr}"
            else:  # Expense
                parent_account = f"Expenses - {company_abbr}"

        # Create the account
        account = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": account_name,
                "account_type": account_type,
                "root_type": root_type,
                "parent_account": parent_account,
                "company": company,
                "is_group": 0,
            }
        )

        account.insert(ignore_permissions=True)
        debug_log(
            f"Created account {full_account_name} under {parent_account}",
            "GL Account Creation",
        )

        return full_account_name

    except Exception as e:
        logger.exception(f"Error creating account {account_name}: {str(e)}")
        debug_log(
            f"Error creating account {account_name}: {str(e)}",
            "GL Account Creation Error",
        )
        return None


def find_parent_account(company, account_type, root_type):
    """
    Find an appropriate parent account based on type and root type

    Args:
        company (str): Company name
        account_type (str): Account type to look for
        root_type (str): Root type of the account

    Returns:
        str: Parent account name or None if not found
    """
    company_abbr = frappe.get_cached_value("Company", company, "abbr")

    # Try to find accounts with specified type and root type
    accounts = frappe.get_all(
        "Account",
        filters={"company": company, "is_group": 1, "root_type": root_type},
        fields=["name", "account_type"],
    )

    # Try to find best match
    for account in accounts:
        if account.account_type == account_type:
            return account.name

    # Try to find standard parent accounts
    standard_parents = {
        "Expense": [
            f"Direct Expenses - {company_abbr}",
            f"Indirect Expenses - {company_abbr}",
            f"Expenses - {company_abbr}",
        ],
        "Liability": [
            f"Current Liabilities - {company_abbr}",
            f"Duties and Taxes - {company_abbr}",
            f"Liabilities - {company_abbr}",
        ],
        "Asset": [f"Current Assets - {company_abbr}", f"Assets - {company_abbr}"],
    }

    if root_type in standard_parents:
        for parent in standard_parents[root_type]:
            if frappe.db.exists("Account", parent):
                return parent

    # No suitable parent found
    return None
