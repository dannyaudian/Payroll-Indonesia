# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
"""Core helpers for GL account mapping."""

import logging
import json

import frappe

from payroll_indonesia.constants import BPJS_ACCOUNT_FIELDS
from payroll_indonesia.config.config import get_config as get_default_config
from functools import lru_cache
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _determine_bpjs_field_name(salary_component: str) -> str:
    component = salary_component.lower()
    if "kesehatan" in component:
        return (
            "kesehatan_employer_debit_account"
            if "employer" in component
            else "kesehatan_employee_account"
        )
    elif "jht" in component:
        return "jht_employer_debit_account" if "employer" in component else "jht_employee_account"
    elif "jp" in component:
        return "jp_employer_debit_account" if "employer" in component else "jp_employee_account"
    elif "jkk" in component:
        return "jkk_employer_debit_account"
    elif "jkm" in component:
        return "jkm_employer_debit_account"
    return ""


def _get_bpjs_account_mapping(company: str, salary_component: str) -> str:
    try:
        field_name = _determine_bpjs_field_name(salary_component)
        if not field_name or field_name not in BPJS_ACCOUNT_FIELDS:
            return ""

        mapping = frappe.get_all(
            "BPJS Account Mapping", filters={"company": company}, fields=[field_name]
        )
        if not mapping:
            return ""
        return mapping[0].get(field_name, "")
    except Exception as e:  # pragma: no cover - defensive
        logger.exception(f"Error getting BPJS account mapping: {e}")
        return ""


def _map_component_to_account(component_name: str, company: str, account_name: str) -> None:
    try:
        component = frappe.get_doc("Salary Component", component_name)

        if hasattr(component, "accounts") and isinstance(component.accounts, list):
            row = next((a for a in component.accounts if a.get("company") == company), None)
            if row:
                if not row.get("default_account"):
                    row.default_account = account_name
            else:
                component.append(
                    "accounts",
                    {
                        "company": company,
                        "default_account": account_name,
                    },
                )
        elif hasattr(component, "default_account") and not getattr(
            component, "default_account", None
        ):
            component.default_account = account_name
        elif hasattr(component, "account") and not getattr(component, "account", None):
            component.account = account_name

        component.flags.ignore_permissions = True
        component.save(ignore_permissions=True)
    except Exception as e:  # pragma: no cover - defensive
        logger.exception(f"Error mapping component {component_name} to account {account_name}: {e}")


@lru_cache(maxsize=1)
def get_account_mapping_from_defaults(bilingual: bool = True) -> Dict[str, str]:
    try:
        config = get_default_config()
        expense_defs = config.get("gl_accounts", {}).get("expense_accounts", {})
    except Exception as e:  # pragma: no cover - defensive
        logger.exception(f"Error loading defaults for account mapping: {e}")
        return {}

    base_map = {
        "Gaji Pokok": "beban_gaji_pokok",
        "Tunjangan Makan": "beban_tunjangan_makan",
        "Tunjangan Transport": "beban_tunjangan_transport",
        "Insentif": "beban_insentif",
        "Bonus": "beban_bonus",
        "Tunjangan Jabatan": "beban_tunjangan_jabatan",
        "Tunjangan Lembur": "beban_tunjangan_lembur",
        "Uang Makan": "beban_natura",
        "Fasilitas Kendaraan": "beban_fasilitas_kendaraan",
    }

    english_equiv = {
        "Basic Salary": "Gaji Pokok",
        "Meal Allowance": "Tunjangan Makan",
        "Transport Allowance": "Tunjangan Transport",
        "Incentive": "Insentif",
        "Position Allowance": "Tunjangan Jabatan",
        "Overtime Allowance": "Tunjangan Lembur",
        "Meal Money": "Uang Makan",
        "Vehicle Facility": "Fasilitas Kendaraan",
    }

    mapping: Dict[str, str] = {}
    for indo_name, key in base_map.items():
        info = expense_defs.get(key) or {}
        account_name = info.get("account_name")
        if not account_name:
            continue
        mapping[indo_name] = account_name
        if bilingual:
            for eng, indo in english_equiv.items():
                if indo == indo_name:
                    mapping[eng] = account_name

    return mapping


def _seed_gl_account_mappings(settings: "frappe.Document", defaults: Dict[str, Any]) -> bool:
    try:
        changes_made = False

        gl_accounts = defaults.get("gl_accounts", {})
        bpjs_gl_accounts = defaults.get("bpjs", {}).get("gl_accounts", {})

        mappings = [
            ("bpjs_account_mapping_json", bpjs_gl_accounts),
            ("expense_accounts_json", gl_accounts.get("expense_accounts", {})),
            ("payable_accounts_json", gl_accounts.get("payable_accounts", {})),
            ("parent_accounts_json", gl_accounts.get("root_account", {})),
        ]

        for field, value in mappings:
            if hasattr(settings, field) and not getattr(settings, field) and value:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, indent=2)
                setattr(settings, field, value)
                changes_made = True

        settings_cfg = defaults.get("settings", {})
        candidate_fields = [
            (
                "parent_account_candidates_expense",
                settings_cfg.get("parent_account_candidates_expense"),
            ),
            (
                "parent_account_candidates_liability",
                settings_cfg.get("parent_account_candidates_liability"),
            ),
            (
                "expense_account_prefix",
                settings_cfg.get("expense_account_prefix"),
            ),
        ]

        for field, value in candidate_fields:
            if hasattr(settings, field) and not getattr(settings, field) and value is not None:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, indent=2)
                setattr(settings, field, value)
                changes_made = True

        if hasattr(settings, "gl_account_mappings"):
            if not settings.gl_account_mappings:
                expense_accounts = gl_accounts.get("expense_accounts", {})
                for key, info in expense_accounts.items():
                    if isinstance(info, dict) and "account_name" in info:
                        settings.append("gl_account_mappings", {
                            "account_key": key,
                            "category": "expense_accounts",
                            "account_name": info.get("account_name"),
                            "account_type": info.get("account_type", "Direct Expense"),
                            "root_type": info.get("root_type", "Expense"),
                            "is_group": info.get("is_group", 0)
                        })
                        changes_made = True

                payable_accounts = gl_accounts.get("payable_accounts", {})
                for key, info in payable_accounts.items():
                    if isinstance(info, dict) and "account_name" in info:
                        settings.append("gl_account_mappings", {
                            "account_key": key,
                            "category": "payable_accounts",
                            "account_name": info.get("account_name"),
                            "account_type": info.get("account_type", "Payable"),
                            "root_type": info.get("root_type", "Liability"),
                            "is_group": info.get("is_group", 0)
                        })
                        changes_made = True

                bpjs_expense = gl_accounts.get("bpjs_expense_accounts", {})
                for key, info in bpjs_expense.items():
                    if isinstance(info, dict) and "account_name" in info:
                        settings.append("gl_account_mappings", {
                            "account_key": key,
                            "category": "bpjs_expense_accounts",
                            "account_name": info.get("account_name"),
                            "account_type": info.get("account_type", "Direct Expense"),
                            "root_type": info.get("root_type", "Expense"),
                            "is_group": info.get("is_group", 0)
                        })
                        changes_made = True

                bpjs_payable = gl_accounts.get("bpjs_payable_accounts", {})
                for key, info in bpjs_payable.items():
                    if isinstance(info, dict) and "account_name" in info:
                        settings.append("gl_account_mappings", {
                            "account_key": key,
                            "category": "bpjs_payable_accounts",
                            "account_name": info.get("account_name"),
                            "account_type": info.get("account_type", "Payable"),
                            "root_type": info.get("root_type", "Liability"),
                            "is_group": info.get("is_group", 0)
                        })
                        changes_made = True

        return changes_made

    except Exception as e:
        logger.error(f"Error updating GL account mappings: {str(e)}")
        raise
