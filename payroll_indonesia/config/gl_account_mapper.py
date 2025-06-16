# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-24 06:02:26 by dannyaudian

import frappe
import logging
from frappe import _
from typing import Dict, Any, Optional

# Import utility function for config
from payroll_indonesia.payroll_indonesia.utils import get_default_config, debug_log

# Setup logger
logger = logging.getLogger(__name__)


def map_gl_account(company: str, account_key: str, category: str) -> str:
    """
    Maps a base account key to a company-specific GL account.

    Args:
        company (str): The company name for which to create the account mapping
        account_key (str): The key of the base account in defaults.json
        category (str): The category of the account (e.g., 'expense_accounts', 'payable_accounts')

    Returns:
        str: The mapped account name with company suffix
    """
    try:
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

        # Return the formatted account name with company
        return f"{account_name} - {company}"

    except Exception as e:
        logger.exception(f"Error mapping GL account for {account_key} in {category}: {str(e)}")
        debug_log(
            f"Error mapping GL account for {account_key} in {category}: {str(e)}",
            "GL Account Mapping Error",
            trace=True,
        )
        # Return fallback format using account_key as name
        return f"{account_key} - {company}"


def get_gl_account_for_salary_component(company: str, salary_component: str) -> str:
    """
    Maps a salary component to its corresponding GL account for a specific company.

    Args:
        company (str): The company name
        salary_component (str): The name of the salary component

    Returns:
        str: The mapped GL account with company suffix
    """
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
        "BPJS JHT Employee": ("bpjs_jht_payable", "bpjs_payable_accounts"),
        "BPJS JP Employee": ("bpjs_jp_payable", "bpjs_payable_accounts"),
        "BPJS Kesehatan Employee": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
        # Employer Contributions (Statistical Components)
        "BPJS JHT Employer": ("bpjs_jht_employer_expense", "bpjs_expense_accounts"),
        "BPJS JP Employer": ("bpjs_jp_employer_expense", "bpjs_expense_accounts"),
        "BPJS JKK": ("bpjs_jkk_employer_expense", "bpjs_expense_accounts"),
        "BPJS JKM": ("bpjs_jkm_employer_expense", "bpjs_expense_accounts"),
        "BPJS Kesehatan Employer": ("bpjs_kesehatan_employer_expense", "bpjs_expense_accounts"),
    }

    # Check if the salary component exists in the mapping
    if salary_component not in component_mapping:
        logger.warning(f"No GL account mapping found for salary component '{salary_component}'")
        debug_log(
            f"No GL account mapping found for salary component '{salary_component}'",
            "Salary Component Mapping",
        )
        return f"{salary_component} Account - {company}"

    # Get the account key and category
    account_key, category = component_mapping[salary_component]

    # Return the mapped GL account
    return map_gl_account(company, account_key, category)
