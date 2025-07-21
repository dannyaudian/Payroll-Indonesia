# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 13:19:43 by dannyaudian

import frappe
import logging
import re
from frappe.exceptions import ValidationError
from typing import Optional

from payroll_indonesia.config.config import (
    get_config as get_default_config,
    get_component_tax_effect,
    get_live_config,
)
from payroll_indonesia.config.gl_mapper_core import (
    _map_component_to_account as core_map_component_to_account,
    _determine_bpjs_field_name as core_determine_bpjs_field_name,
    _get_bpjs_account_mapping as core_get_bpjs_account_mapping,
    get_account_mapping_from_defaults as core_get_account_mapping,
)
from payroll_indonesia.payroll_indonesia.utils import (
    debug_log,
    get_or_create_account,
)

logger = logging.getLogger(__name__)

def _determine_bpjs_field_name(salary_component: str) -> str:
    return core_determine_bpjs_field_name(salary_component)

def _get_bpjs_account_mapping(company: str, salary_component: str) -> str:
    return core_get_bpjs_account_mapping(company, salary_component)

def _map_component_to_account(component_name: str, company: str, account_name: str) -> None:
    return core_map_component_to_account(component_name, company, account_name)

def map_gl_account(company: str, account_key: str, category: str) -> str:
    try:
        if "bpjs" in account_key.lower() or category.startswith("bpjs_"):
            debug_log(
                f"Skipping BPJS account mapping for {account_key} as it's handled by BPJSAccountMapping DocType",
                "GL Account Mapping",
            )
            return ""

        if frappe.db.exists("Payroll Indonesia Settings", "Payroll Indonesia Settings"):
            settings = frappe.get_cached_doc("Payroll Indonesia Settings")
            for mapping in settings.gl_account_mappings:
                if mapping.account_key == account_key and mapping.category == category:
                    account_info = {
                        "account_name": mapping.account_name,
                        "account_type": mapping.account_type,
                        "root_type": mapping.root_type,
                        "is_group": mapping.is_group,
                    }

                    company_abbr = frappe.get_cached_value("Company", company, "abbr")
                    formatted_account_name = f"{account_info['account_name']} - {company_abbr}"

                    if not frappe.db.exists("Account", formatted_account_name):
                        get_or_create_account(
                            company,
                            account_info["account_name"],
                            account_info.get("account_type", "Expense Account"),
                            account_info.get("root_type", "Expense"),
                            is_group=account_info.get("is_group", 0),
                        )

                    return formatted_account_name

        config = get_default_config()
        if not config:
            logger.warning("Could not load defaults.json configuration")
            debug_log(
                f"Could not load defaults.json configuration when mapping {account_key}",
                "GL Account Mapping",
        )
            return f"{account_key} - {company}"

        gl_accounts = config.get("gl_accounts", {})
        if not gl_accounts:
            logger.warning("No gl_accounts found in configuration")
            debug_log("No gl_accounts found in configuration", "GL Account Mapping")
            return f"{account_key} - {company}"

        if category not in gl_accounts:
            logger.warning(f"Category '{category}' not found in gl_accounts configuration")
            debug_log(
                f"Category '{category}' not found in gl_accounts configuration",
                "GL Account Mapping",
            )
            return f"{account_key} - {company}"

        category_accounts = gl_accounts[category]
        if account_key not in category_accounts:
            logger.warning(f"Account key '{account_key}' not found in '{category}' category")
            debug_log(
                f"Account key '{account_key}' not found in '{category}' category",
                "GL Account Mapping",
            )
            return f"{account_key} - {company}"

        account_info = category_accounts[account_key]
        if not isinstance(account_info, dict) or "account_name" not in account_info:
            logger.warning(f"Invalid account info or missing account_name for {account_key}")
            debug_log(
                f"Invalid account info or missing account_name for {account_key}",
                "GL Account Mapping",
            )
            return f"{account_key} - {company}"

        account_name = account_info["account_name"]
        company_abbr = frappe.get_cached_value("Company", company, "abbr")
        formatted_account_name = f"{account_name} - {company_abbr}"

        if not frappe.db.exists("Account", formatted_account_name):
            account_type = account_info.get("account_type", "Expense Account")
            root_type = account_info.get("root_type", "Expense")
            default_parent = "Expenses - " + company_abbr
            if root_type == "Liability":
                default_parent = "Liabilities - " + company_abbr
            elif root_type == "Asset":
                default_parent = "Assets - " + company_abbr

            get_or_create_account(company, account_name, account_type, root_type, default_parent)

        return formatted_account_name

    except Exception as e:
        logger.exception(f"Error mapping GL account for {account_key} in {category}: {str(e)}")
        debug_log(
            f"Error mapping GL account for {account_key} in {category}: {str(e)}",
            "GL Account Mapping Error",
        )
        return f"{account_key} - {company}"

def get_expense_account_for_component(component_name: str) -> Optional[str]:
    try:
        mapping = core_get_account_mapping()
        return mapping.get(component_name)
    except Exception as e:
        logger.exception(f"Error getting expense account for {component_name}: {e}")
        return None

def get_gl_account_for_salary_component(company: str, salary_component: str) -> str:
    account = frappe.db.get_value(
        "Salary Component Account",
        {"company": company, "parent": salary_component},
        "default_account",
    )
    if account:
        return account

    bpjs_account = _get_bpjs_account_mapping(company, salary_component)
    if bpjs_account:
        debug_log(
            f"Using BPJS account mapping for {salary_component}: {bpjs_account}",
            "Salary Component Mapping",
        )
        return bpjs_account

    component_mapping = {
        "Gaji Pokok": ("beban_gaji_pokok", "expense_accounts"),
        "Tunjangan Makan": ("beban_tunjangan_makan", "expense_accounts"),
        "Tunjangan Transport": ("beban_tunjangan_transport", "expense_accounts"),
        "Insentif": ("beban_insentif", "expense_accounts"),
        "Bonus": ("beban_bonus", "expense_accounts"),
        "Tunjangan Jabatan": ("beban_tunjangan_jabatan", "expense_accounts"),
        "Tunjangan Lembur": ("beban_tunjangan_lembur", "expense_accounts"),
        "Uang Makan": ("beban_natura", "expense_accounts"),
        "Fasilitas Kendaraan": ("beban_fasilitas_kendaraan", "expense_accounts"),
        "Basic Salary": ("beban_gaji_pokok", "expense_accounts"),
        "Meal Allowance": ("beban_tunjangan_makan", "expense_accounts"),
        "Transport Allowance": ("beban_tunjangan_transport", "expense_accounts"),
        "Incentive": ("beban_insentif", "expense_accounts"),
        "Position Allowance": ("beban_tunjangan_jabatan", "expense_accounts"),
        "Overtime Allowance": ("beban_tunjangan_lembur", "expense_accounts"),
        "Meal Money": ("beban_natura", "expense_accounts"),
        "Vehicle Facility": ("beban_fasilitas_kendaraan", "expense_accounts"),
        "PPh 21": ("hutang_pph21", "payable_accounts"),
        "Potongan Kasbon": ("hutang_kasbon", "payable_accounts"),
    }

    component_doc = None
    try:
        component_doc = frappe.get_doc("Salary Component", salary_component)
    except Exception as e:
        logger.warning(f"Could not load salary component {salary_component}: {str(e)}")

    component_type = "Earning"
    if component_doc and hasattr(component_doc, "type"):
        component_type = component_doc.type

    tax_effect = get_component_tax_effect(salary_component, component_type)

    if salary_component not in component_mapping:
        cfg = get_live_config()
        prefix_val = cfg.get("expense_account_prefix") or "Beban"
        if isinstance(prefix_val, str):
            parts = [p.strip() for p in re.split(r",|\n", prefix_val) if p.strip()]
            prefix = parts[0] if parts else "Expense"
        else:
            prefix = str(prefix_val)

        if tax_effect == "Penambah Bruto/Objek Pajak":
            base_name = f"{prefix} {salary_component}"
        elif tax_effect == "Pengurang Netto/Tax Deduction":
            base_name = f"{prefix} {salary_component}"
        elif tax_effect == "Natura/Fasilitas (Objek Pajak)":
            base_name = f"{prefix} Natura {salary_component}"
        elif tax_effect == "Natura/Fasilitas (Non-Objek Pajak)":
            base_name = f"{prefix} Fasilitas {salary_component}"
        else:
            base_name = f"{salary_component} Account"

        return get_or_create_account(company, base_name, "Expense Account", "Expense")

    account_key, category = component_mapping[salary_component]
    return map_gl_account(company, account_key, category)

def map_salary_component_to_gl(company: str, gl_defaults: Optional[dict] | None = None) -> list[str]:
    try:
        if gl_defaults is None:
            gl_defaults = get_default_config() or {}

        expense_defs = gl_defaults.get("gl_accounts", {}).get("expense_accounts", {})
        if not expense_defs:
            logger.warning(f"No expense_accounts definitions found in gl_defaults for {company}")
            return []

        mapping = core_get_account_mapping()
        if not mapping:
            logger.warning(f"No account mapping found for {company}")
            return []

        components = frappe.get_all("Salary Component", filters={"disabled": 0}, pluck="name")
        mapped: list[str] = []

        for comp in components:
            account_base = mapping.get(comp)
            if not account_base:
                key = re.sub(r"[^a-z0-9]+", "_", comp.lower()).strip("_")
                logger.debug(f"Component {comp} not found in mapping, using fallback key: {key}")
                continue

            key = re.sub(r"[^a-z0-9]+", "_", account_base.lower()).strip("_")
            info = expense_defs.get(key, {})

            account_type = info.get("account_type", "Expense Account")
            root_type = info.get("root_type", "Expense")

            full_name = get_or_create_account(
                company,
                account_base,
                account_type=account_type,
                root_type=root_type,
            )

            if not full_name:
                logger.warning(f"Failed to create/get account for component {comp} in {company}")
                continue

            _map_component_to_account(comp, company, full_name)
            mapped.append(comp)
            logger.info(f"Successfully mapped {comp} to {full_name} in {company}")

        if not mapped:
            logger.warning(f"No salary components were mapped for {company}")
        else:
            logger.info(f"Mapped {len(mapped)} salary components for {company}")
        return mapped
    except Exception as e:
        logger.exception(f"Error mapping salary components for {company}: {e}")
        frappe.log_error(
            f"Error mapping salary components for {company}: {e}",
            "Salary Component Mapping Error"
        )
        return []
