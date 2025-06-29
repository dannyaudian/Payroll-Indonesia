# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 00:38:07 by dannyaudian

"""
Core utility functions for the Payroll Indonesia module.

This module provides common functions used by various components of 
Payroll Indonesia, with a focus on separating configuration from business logic.
"""

import logging
import os
from typing import Dict, Any, List, Optional, Union, Tuple, cast

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, now_datetime

from payroll_indonesia.config import get_live_config
from payroll_indonesia.frappe_helpers import (
    safe_execute,
    ensure_doc_exists,
    doc_exists
)

# Configure logger
logger = logging.getLogger('payroll_utils')


# =========== ACCOUNT AND GL FUNCTIONS ===========

@safe_execute(default_value=None, log_exception=True)
def get_or_create_account(
    company: str,
    account_name: str,
    account_type: str = "Payable",
    is_group: int = 0,
    root_type: Optional[str] = None
) -> Optional[str]:
    """
    Get or create a GL account if it doesn't exist.
    
    Args:
        company: Company name
        account_name: Account name without company prefix
        account_type: Account type (Payable, Expense, etc.)
        is_group: Whether the account is a group (1) or not (0)
        root_type: Root type (will be determined from account_type if None)
        
    Returns:
        str: Full account name, None if failed
    """
    # Validate parameters
    if not company or not account_name:
        logger.error("Company and account_name are required")
        return None
    
    # Get company abbreviation
    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        logger.error(f"Company {company} does not have an abbreviation")
        return None
    
    # Create full account name
    full_account_name = f"{account_name} - {abbr}"
    
    # Check if account already exists
    if frappe.db.exists("Account", full_account_name):
        logger.info(f"Account {full_account_name} already exists")
        return full_account_name
    
    # Determine root_type if not provided
    if not root_type:
        if account_type in ["Payable", "Tax", "Receivable"]:
            root_type = "Liability"
        elif account_type in ["Expense", "Expense Account"]:
            root_type = "Expense"
        elif account_type in ["Income", "Income Account"]:
            root_type = "Income"
        elif account_type == "Asset":
            root_type = "Asset"
        else:
            root_type = "Liability"  # Default
    
    # Find parent account
    parent = find_parent_account(company, account_type, root_type)
    if not parent:
        logger.error(
            f"Cannot find parent account for {account_name}"
        )
        return None
    
    # Create account object
    account_data = {
        "doctype": "Account",
        "account_name": account_name,
        "company": company,
        "parent_account": parent,
        "is_group": cint(is_group),
        "root_type": root_type,
        "account_currency": frappe.get_cached_value(
            "Company", company, "default_currency"
        ),
    }
    
    # Add account_type for non-group accounts
    if not is_group and account_type:
        account_data["account_type"] = account_type
    
    # Create account
    try:
        doc = frappe.get_doc(account_data)
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        logger.info(f"Successfully created account: {full_account_name}")
        return full_account_name
    except Exception as e:
        logger.error(f"Failed to create account {full_account_name}: {str(e)}")
        return None


@safe_execute(default_value=None, log_exception=True)
def find_parent_account(
    company: str,
    account_type: str,
    root_type: Optional[str] = None
) -> Optional[str]:
    """
    Find appropriate parent account based on type.
    
    Args:
        company: Company name
        account_type: Account type (Payable, Expense, etc.)
        root_type: Root type (will be determined from account_type if None)
        
    Returns:
        str: Parent account name, None if not found
    """
    # Determine root_type if not provided
    if not root_type:
        if account_type in ["Payable", "Tax", "Receivable"]:
            root_type = "Liability"
        elif account_type in ["Expense", "Expense Account"]:
            root_type = "Expense"
        elif account_type in ["Income", "Income Account"]:
            root_type = "Income"
        elif account_type == "Asset":
            root_type = "Asset"
        else:
            root_type = "Liability"  # Default
    
    # Get company abbreviation
    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        logger.error(f"Company {company} does not have an abbreviation")
        return None
    
    # Get candidates from configuration
    config = get_live_config()
    parent_candidates = config.get("parent_accounts", {}).get(root_type, [])
    
    # Use defaults if not in configuration
    if not parent_candidates:
        if root_type == "Liability":
            parent_candidates = [
                "Duties and Taxes", "Current Liabilities", "Accounts Payable"
            ]
        elif root_type == "Expense":
            parent_candidates = [
                "Direct Expenses", "Indirect Expenses", "Expenses"
            ]
        elif root_type == "Income":
            parent_candidates = ["Income", "Direct Income", "Indirect Income"]
        elif root_type == "Asset":
            parent_candidates = ["Current Assets", "Fixed Assets"]
        else:
            parent_candidates = []
    
    # Find parent account from candidates
    for candidate in parent_candidates:
        # Check exact account name
        account = frappe.db.get_value(
            "Account",
            {
                "account_name": candidate,
                "company": company,
                "is_group": 1
            },
            "name"
        )
        
        if account:
            return account
        
        # Check with company suffix
        account_with_suffix = f"{candidate} - {abbr}"
        if frappe.db.exists("Account", account_with_suffix):
            return account_with_suffix
    
    # Fallback: find any group account with matching root_type
    accounts = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "is_group": 1,
            "root_type": root_type
        },
        order_by="lft",
        limit=1
    )
    
    if accounts:
        return accounts[0].name
    
    # Ultimate fallback: use company's root account
    root_accounts = {
        "Asset": "Application of Funds (Assets)",
        "Liability": "Source of Funds (Liabilities)",
        "Expense": "Expenses",
        "Income": "Income",
        "Equity": "Equity"
    }
    
    root_account = root_accounts.get(root_type)
    if root_account:
        full_name = f"{root_account} - {abbr}"
        if frappe.db.exists("Account", full_name):
            return full_name
    
    return None


# =========== BPJS FUNCTIONS ===========

@safe_execute(default_value={}, log_exception=True)
def calculate_bpjs(salary: float) -> Dict[str, Any]:
    """
    Calculate BPJS contributions based on salary.
    
    Args:
        salary: Base salary
        
    Returns:
        dict: BPJS contribution details
    """
    # Validate input
    salary = flt(salary)
    if salary < 0:
        logger.warning("Negative salary value, using absolute value")
        salary = abs(salary)
    
    # Get BPJS percentages from configuration
    config = get_live_config()
    bpjs_config = config.get('bpjs', {})
    
    # BPJS Kesehatan
    kesehatan_employee = flt(bpjs_config.get('kesehatan_employee_percent', 1.0))
    kesehatan_employer = flt(bpjs_config.get('kesehatan_employer_percent', 4.0))
    kesehatan_max = flt(bpjs_config.get('kesehatan_max_salary', 12000000))
    
    # BPJS Ketenagakerjaan - JHT
    jht_employee = flt(bpjs_config.get('jht_employee_percent', 2.0))
    jht_employer = flt(bpjs_config.get('jht_employer_percent', 3.7))
    
    # BPJS Ketenagakerjaan - JP
    jp_employee = flt(bpjs_config.get('jp_employee_percent', 1.0))
    jp_employer = flt(bpjs_config.get('jp_employer_percent', 2.0))
    jp_max = flt(bpjs_config.get('jp_max_salary', 9077600))
    
    # BPJS Ketenagakerjaan - JKK and JKM
    jkk = flt(bpjs_config.get('jkk_percent', 0.24))
    jkm = flt(bpjs_config.get('jkm_percent', 0.3))
    
    # Cap salary with maximum limits
    kesehatan_salary = min(salary, kesehatan_max)
    jp_salary = min(salary, jp_max)
    
    # Calculate contributions
    kesehatan_employee_amount = kesehatan_salary * (kesehatan_employee / 100)
    kesehatan_employer_amount = kesehatan_salary * (kesehatan_employer / 100)
    
    jht_employee_amount = salary * (jht_employee / 100)
    jht_employer_amount = salary * (jht_employer / 100)
    
    jp_employee_amount = jp_salary * (jp_employee / 100)
    jp_employer_amount = jp_salary * (jp_employer / 100)
    
    jkk_amount = salary * (jkk / 100)
    jkm_amount = salary * (jkm / 100)
    
    # Result
    return {
        "kesehatan": {
            "employee": kesehatan_employee_amount,
            "employer": kesehatan_employer_amount,
            "total": kesehatan_employee_amount + kesehatan_employer_amount
        },
        "ketenagakerjaan": {
            "jht": {
                "employee": jht_employee_amount,
                "employer": jht_employer_amount,
                "total": jht_employee_amount + jht_employer_amount
            },
            "jp": {
                "employee": jp_employee_amount,
                "employer": jp_employer_amount,
                "total": jp_employee_amount + jp_employer_amount
            },
            "jkk": jkk_amount,
            "jkm": jkm_amount
        },
        "total_employee": (
            kesehatan_employee_amount + jht_employee_amount + jp_employee_amount
        ),
        "total_employer": (
            kesehatan_employer_amount + jht_employer_amount + 
            jp_employer_amount + jkk_amount + jkm_amount
        )
    }


@safe_execute(default_value=False, log_exception=True)
def validate_bpjs_limits(
    component: str,
    value: float,
    field_type: str = "percentage"
) -> bool:
    """
    Validate BPJS parameter values based on configuration limits.
    
    Args:
        component: BPJS component (kesehatan_employee, jht_employer, etc.)
        value: Value to validate
        field_type: Value type (percentage or max_salary)
        
    Returns:
        bool: True if valid, False if not
    """
    # Get limits from configuration
    config = get_live_config()
    bpjs_config = config.get('bpjs', {})
    validation = bpjs_config.get('validation', {})
    
    if field_type == "percentage":
        limits = validation.get('percentage_limits', {})
        component_limits = limits.get(component, {})
        
        min_val = component_limits.get('min', 0)
        max_val = component_limits.get('max', 100)
        
        return min_val <= flt(value) <= max_val
    elif field_type == "max_salary":
        limits = validation.get('salary_limits', {})
        component_limits = limits.get(component, {})
        
        min_val = component_limits.get('min', 0)
        max_val = component_limits.get('max', float('inf'))
        
        return min_val <= flt(value) <= max_val
    
    return True


# =========== TAX (PPh 21) FUNCTIONS ===========

@safe_execute(default_value=None, log_exception=True)
def get_ptkp_value(tax_status: str) -> Optional[float]:
    """
    Get PTKP value based on tax status.
    
    Args:
        tax_status: Tax status code (TK0, K1, etc.)
        
    Returns:
        float: Annual PTKP value, None if not found
    """
    # Get PTKP values from configuration
    config = get_live_config()
    ptkp_values = config.get('ptkp', {})
    
    # If tax status exists in configuration, use that value
    if tax_status in ptkp_values:
        return flt(ptkp_values[tax_status])
    
    # If not in configuration, use default values
    default_values = {
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
        "HB3": 126000000
    }
    
    return flt(default_values.get(tax_status))


@safe_execute(default_value=[], log_exception=True)
def get_tax_brackets() -> List[Dict[str, Any]]:
    """
    Get progressive tax brackets for PPh 21.
    
    Returns:
        list: List of tax brackets with income_from, income_to, and tax_rate
    """
    # Get tax brackets from configuration
    config = get_live_config()
    brackets = config.get('tax_brackets', [])
    
    # If in configuration, sort and use
    if brackets:
        # Sort by income_from
        return sorted(brackets, key=lambda x: x["income_from"])
    
    # If not in configuration, use default values
    return [
        {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
        {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
        {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
        {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
        {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
    ]


@safe_execute(default_value="TER C", log_exception=True)
def get_ter_category(tax_status: str) -> str:
    """
    Map PTKP status to TER category.
    
    Args:
        tax_status: Tax status code (TK0, K1, etc.)
        
    Returns:
        str: TER category ("TER A", "TER B", or "TER C")
    """
    # Get mapping from configuration
    config = get_live_config()
    ptkp_to_ter = config.get('ptkp_to_ter_mapping', {})
    
    # If in configuration, use it
    if tax_status in ptkp_to_ter:
        return ptkp_to_ter[tax_status]
    
    # If not in configuration, use default logic
    prefix = tax_status[:2] if len(tax_status) >= 2 else tax_status
    suffix = tax_status[2:] if len(tax_status) >= 3 else "0"
    
    if tax_status == "TK0":
        return "TER A"
    elif prefix == "TK" and suffix in ["1", "2", "3"]:
        return "TER B"
    elif prefix == "K" and suffix == "0":
        return "TER B"
    elif prefix == "K" and suffix in ["1", "2", "3"]:
        return "TER C"
    elif prefix == "HB":  # Single parent
        return "TER C"
    
    # Default: highest category
    return "TER C"


@safe_execute(default_value=0.0, log_exception=True)
def calculate_ter(tax_status: str, income: float) -> float:
    """
    Calculate TER (Tarif Efektif Rata-rata) tax rate.
    
    Args:
        tax_status: Tax status code (TK0, K1, etc.)
        income: Gross income
        
    Returns:
        float: TER rate as decimal (e.g. 0.05 for 5%)
    """
    # Validate input
    income = flt(income)
    if income <= 0:
        return 0.0
    
    # Get TER category
    ter_category = get_ter_category(tax_status)
    
    # Get TER rates from configuration
    config = get_live_config()
    ter_rates = config.get('ter_rates', {}).get(ter_category, [])
    
    # If rates exist in configuration, find the appropriate one
    if ter_rates:
        # Sort rates by income_from (descending)
        sorted_rates = sorted(
            ter_rates, key=lambda x: x.get("income_from", 0), reverse=True
        )
        
        # Find matching rate
        for rate_data in sorted_rates:
            income_from = flt(rate_data.get("income_from", 0))
            income_to = flt(rate_data.get("income_to", 0))
            is_highest = rate_data.get("is_highest_bracket", False)
            
            if income >= income_from and (
                is_highest or income_to == 0 or income < income_to
            ):
                return flt(rate_data.get("rate", 0)) / 100.0
    
    # If not in configuration, use default rates
    default_rates = {
        "TER A": 0.05,  # 5%
        "TER B": 0.10,  # 10%
        "TER C": 0.15   # 15%
    }
    
    return default_rates.get(ter_category, 0.15)


@safe_execute(default_value=False, log_exception=True)
def should_use_ter(is_december: bool = False) -> bool:
    """
    Check if TER method should be used based on configuration.
    
    Args:
        is_december: Whether this is a December salary slip
        
    Returns:
        bool: True if use TER, False if use Progressive
    """
    # If December, always use Progressive
    if is_december:
        logger.info("December month, using Progressive calculation")
        return False
    
    # Get TER configuration
    config = get_live_config()
    tax_config = config.get('tax', {})
    
    calculation_method = tax_config.get('tax_calculation_method', 'Progressive')
    use_ter = cint(tax_config.get('use_ter', 0))
    
    # Use TER if both match
    return calculation_method == 'TER' and use_ter == 1


@safe_execute(default_value=0.0, log_exception=True)
def calculate_biaya_jabatan(gross_pay: float) -> float:
    """
    Calculate position allowance based on tax rules.
    
    Args:
        gross_pay: Gross income
        
    Returns:
        float: Position allowance value
    """
    # Get parameters from configuration
    config = get_live_config()
    tax_config = config.get('tax', {})
    
    percent = flt(tax_config.get('biaya_jabatan_percent', 5.0))
    max_value = flt(tax_config.get('biaya_jabatan_max', 500000.0))
    
    # Calculate position allowance
    biaya_jabatan = gross_pay * (percent / 100)
    
    # Cap with maximum value
    if biaya_jabatan > max_value:
        biaya_jabatan = max_value
    
    return biaya_jabatan


@safe_execute(default_value=0.0, log_exception=True)
def calculate_progressive_tax(
    yearly_netto: float,
    ptkp: float
) -> float:
    """
    Calculate PPh 21 using progressive method.
    
    Args:
        yearly_netto: Annual net income
        ptkp: Annual PTKP value
        
    Returns:
        float: Annual tax
    """
    # Calculate PKP (Taxable Income)
    pkp = max(0, yearly_netto - ptkp)
    if pkp <= 0:
        return 0.0
    
    # Get tax brackets
    brackets = get_tax_brackets()
    
    # Calculate tax per bracket
    tax = 0.0
    remaining_income = pkp
    
    for bracket in brackets:
        income_from = flt(bracket["income_from"])
        income_to = flt(bracket["income_to"])
        rate = flt(bracket["tax_rate"]) / 100.0
        
        # Last bracket
        if income_to == 0 or income_to > remaining_income:
            tax += remaining_income * rate
            break
        
        # Middle brackets
        taxable_in_bracket = income_to - income_from
        if remaining_income <= taxable_in_bracket:
            tax += remaining_income * rate
            break
        else:
            tax += taxable_in_bracket * rate
            remaining_income -= taxable_in_bracket
    
    return tax


# =========== GENERAL UTILITY FUNCTIONS ===========

@safe_execute(default_value=None, log_exception=True)
def get_settings():
    """
    Get Payroll Indonesia Settings document.
    
    Returns:
        Settings document or None if error
    """
    settings_name = "Payroll Indonesia Settings"
    
    if not doc_exists(settings_name, settings_name):
        # Create default settings if doesn't exist
        settings = create_default_settings()
    else:
        settings = frappe.get_doc(settings_name, settings_name)
    
    return settings


@safe_execute(default_value=None, log_exception=True)
def create_default_settings():
    """
    Create default Payroll Indonesia Settings.
    
    Returns:
        Created settings document
    """
    # Get default configuration
    config = get_live_config()
    
    # Extract values with defaults
    bpjs = config.get('bpjs', {})
    tax = config.get('tax', {})
    defaults = config.get('defaults', {})
    
    settings = frappe.get_doc({
        "doctype": "Payroll Indonesia Settings",
        "app_version": "1.0.0",
        "app_last_updated": now_datetime(),
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
        "biaya_jabatan_percent": tax.get("biaya_jabatan_percent", 5.0),
        "biaya_jabatan_max": tax.get("biaya_jabatan_max", 500000.0),
        "tax_calculation_method": tax.get("tax_calculation_method", "TER"),
        "use_ter": tax.get("use_ter", 1),
        
        # Default settings
        "default_currency": defaults.get("currency", "IDR"),
        "payroll_frequency": defaults.get("payroll_frequency", "Monthly"),
        "max_working_days_per_month": defaults.get("max_working_days", 22),
        "working_hours_per_day": defaults.get("working_hours", 8),
    })
    
    # Insert with permission bypass
    settings.flags.ignore_permissions = True
    settings.flags.ignore_mandatory = True
    settings.insert(ignore_permissions=True)
    
    frappe.db.commit()
    return settings


@safe_execute(default_value=None, log_exception=True)
def get_employee_details(employee_id: str) -> Optional[Dict[str, Any]]:
    """
    Get employee details with tax and BPJS data.
    
    Args:
        employee_id: Employee ID
        
    Returns:
        dict: Employee details, None if not found
    """
    # Ensure employee exists
    if not frappe.db.exists("Employee", employee_id):
        logger.warning(f"Employee {employee_id} not found")
        return None
    
    # Get employee document
    employee = frappe.get_doc("Employee", employee_id)
    
    # Extract relevant information
    result = {
        "name": employee.name,
        "employee_name": employee.employee_name,
        "company": employee.company,
        "department": employee.department,
        "designation": employee.designation,
        "status_pajak": getattr(employee, "status_pajak", "TK0"),
        "npwp": getattr(employee, "npwp", ""),
        "ktp": getattr(employee, "ktp", ""),
        "ikut_bpjs_kesehatan": cint(
            getattr(employee, "ikut_bpjs_kesehatan", 1)
        ),
        "ikut_bpjs_ketenagakerjaan": cint(
            getattr(employee, "ikut_bpjs_ketenagakerjaan", 1)
        ),
    }
    
    return result


def get_month_name(month: int) -> str:
    """
    Get month name from month number.
    
    Args:
        month: Month number (1-12)
        
    Returns:
        str: Month name
    """
    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    
    if 1 <= month <= 12:
        return month_names[month - 1]
    
    return f"Month {month}"
