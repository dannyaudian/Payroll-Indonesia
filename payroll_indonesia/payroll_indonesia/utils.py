# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
General Payroll Indonesia helpers: account, utils, and decorator.
No tax/BPJS-specific functions.
"""

import logging
from typing import Any, Callable, Optional, Dict, TypeVar, cast
import frappe

from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.frappe_helpers import ensure_doc_exists

logger = logging.getLogger("payroll_utils")
F = TypeVar("F", bound=Callable[..., Any])


def safe_execute(
    default_value: Any = None, log_exception: bool = True
) -> Callable[[F], F]:
    """
    Decorator to safely execute a function.
    Returns default_value on Exception.
    """

    def decorator(func: F) -> F:
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_exception:
                    logger.error(
                        f"Error in {func.__name__}: {e}", exc_info=True
                    )
                return default_value

        return cast(F, wrapper)

    return decorator


@safe_execute(default_value=None, log_exception=True)
def get_or_create_account(
    company: str,
    account_name: str,
    account_type: str = "Payable",
    is_group: int = 0,
    root_type: Optional[str] = None,
) -> Optional[str]:
    """
    Get or create Account, return full account name.

    Args:
        company: Company name
        account_name: Account name (without company suffix)
        account_type: Payable/Expense/Income/Asset/etc.
        is_group: 1 for group account, 0 otherwise
        root_type: Asset/Liability/Expense/Income

    Returns:
        str: Full account name, or None if failed
    """
    if not company or not account_name:
        logger.error("Company & account_name required")
        return None

    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        logger.error(f"Company {company} has no abbreviation")
        return None

    full_name = f"{account_name} - {abbr}"
    if frappe.db.exists("Account", full_name):
        logger.info(f"Account {full_name} exists")
        return full_name

    if not root_type:
        if account_type in {"Payable", "Tax", "Receivable"}:
            root_type = "Liability"
        elif account_type in {"Expense", "Expense Account"}:
            root_type = "Expense"
        elif account_type in {"Income", "Income Account"}:
            root_type = "Income"
        elif account_type == "Asset":
            root_type = "Asset"
        else:
            root_type = "Liability"

    parent = _find_parent_account(company, account_type, root_type)
    if not parent:
        logger.error(f"Parent account not found for {account_name}")
        return None

    acc_data = {
        "doctype": "Account",
        "account_name": account_name,
        "company": company,
        "parent_account": parent,
        "is_group": is_group,
        "root_type": root_type,
        "account_currency": frappe.get_cached_value(
            "Company", company, "default_currency"
        ),
    }
    if not is_group and account_type:
        acc_data["account_type"] = account_type

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


def _find_parent_account(
    company: str, account_type: str, root_type: Optional[str] = None
) -> Optional[str]:
    """
    Find parent account based on type/root_type.
    """
    if not root_type:
        if account_type in {"Payable", "Tax", "Receivable"}:
            root_type = "Liability"
        elif account_type in {"Expense", "Expense Account"}:
            root_type = "Expense"
        elif account_type in {"Income", "Income Account"}:
            root_type = "Income"
        elif account_type == "Asset":
            root_type = "Asset"
        else:
            root_type = "Liability"

    abbr = frappe.get_cached_value("Company", company, "abbr")
    if not abbr:
        logger.error(f"Company {company} has no abbreviation")
        return None

    config = get_live_config()
    parent_candidates = config.get("parent_accounts", {}).get(root_type, [])
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
            parent_candidates = [
                "Income", "Direct Income", "Indirect Income"
            ]
        elif root_type == "Asset":
            parent_candidates = ["Current Assets", "Fixed Assets"]
        else:
            parent_candidates = []

    for cand in parent_candidates:
        acc = frappe.db.get_value(
            "Account",
            {"account_name": cand, "company": company, "is_group": 1},
            "name",
        )
        if acc:
            return acc
        acc_w_sfx = f"{cand} - {abbr}"
        if frappe.db.exists("Account", acc_w_sfx):
            return acc_w_sfx

    accs = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "is_group": 1,
            "root_type": root_type,
        },
        order_by="lft",
        limit=1,
    )
    if accs:
        return accs[0].name

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


def rupiah_format(amount: Any) -> str:
    """
    Format number as Rupiah (Rp) string.
    """
    try:
        value = float(amount)
    except Exception:
        value = 0.0
    return f"Rp {value:,.0f}".replace(",", ".")


def safe_int(val: Any, default: int = 0) -> int:
    """
    Safely convert to int, return default if failed.
    """
    try:
        return int(float(val))
    except Exception:
        return default
