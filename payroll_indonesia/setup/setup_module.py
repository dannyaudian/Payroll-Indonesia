# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
setup_module.py – basic setup routines for Payroll Indonesia.
Provides minimal setup functions used during installation and migration.
"""

from typing import Dict, Any, Optional, List
import os
import json
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import now_datetime

from payroll_indonesia.frappe_helpers import get_logger
logger = get_logger("setup")

from payroll_indonesia.utilities.tax_slab import setup_income_tax_slab
from payroll_indonesia.setup.settings_migration import _load_defaults
from payroll_indonesia.config.config import doctype_defined

def setup_module() -> bool:
    logger.info("Starting Payroll Indonesia basic setup")
    results = [
        create_custom_workspace(),
        setup_default_modules(),
        ensure_settings_doctype_exists(),
    ]
    success = all(results)
    if success:
        logger.info("Payroll Indonesia basic setup completed successfully")
    else:
        logger.warning("Payroll Indonesia basic setup completed with warnings")
    return success

def setup_accounts() -> bool:
    logger.info("Setting up Payroll Indonesia tax infrastructure")
    results = {"income_tax_slab": False, "pph21_ter": False}
    try:
        defaults = frappe.defaults.get_defaults()
        logger.info("Obtained system defaults for tax setup")
    except Exception as e:
        logger.warning(f"Could not get system defaults, falling back to config: {str(e)}")
        defaults = {}
    config_defaults = _load_defaults()
    if config_defaults:
        for key, value in config_defaults.items():
            if key not in defaults:
                defaults[key] = value
    try:
        result = setup_income_tax_slab(defaults)
        results["income_tax_slab"] = result
        if result:
            logger.info("Income Tax Slab setup completed successfully")
        else:
            logger.info("Income Tax Slab setup skipped (already exists)")
    except Exception as e:
        logger.error(f"Error setting up Income Tax Slab: {str(e)}")
        frappe.log_error(f"Error setting up Income Tax Slab: {str(e)}", "Tax Setup Error")
    try:
        from payroll_indonesia.fixtures.setup import setup_pph21_ter
        result = setup_pph21_ter(defaults)
        results["pph21_ter"] = result
        if result:
            logger.info("PPh 21 TER rates setup completed successfully")
        else:
            logger.info("PPh 21 TER rates setup skipped (already exists)")
    except Exception as e:
        logger.error(f"Error setting up PPh 21 TER rates: {str(e)}")
        frappe.log_error(f"Error setting up PPh 21 TER rates: {str(e)}", "TER Setup Error")
    success = any(results.values())
    if success:
        logger.info("Payroll Indonesia tax infrastructure setup completed")
    else:
        logger.warning("Payroll Indonesia tax infrastructure setup completed with warnings")
    return success

def create_custom_workspace() -> bool:
    try:
        logger.info("Setting up Payroll Indonesia workspace")
        if not frappe.db.exists("DocType", "Workspace"):
            logger.warning("Workspace DocType does not exist")
            return False
        workspace_name = "Payroll Indonesia"
        if frappe.db.exists("Workspace", workspace_name):
            logger.info(f"Workspace '{workspace_name}' already exists")
            return True
        workspace = frappe.new_doc("Workspace")
        workspace.name = workspace_name
        workspace.label = workspace_name
        workspace.category = "Modules"
        workspace.icon = "payroll"
        workspace.module = "Payroll Indonesia"
        workspace.onboarding = "Payroll Indonesia"
        workspace.is_hidden = 0
        workspace.for_user = ""
        workspace.append(
            "links",
            {
                "label": _("Payroll Settings"),
                "link_type": "DocType",
                "link_to": "Payroll Indonesia Settings",
                "onboard": 1,
                "dependencies": "",
                "is_query_report": 0,
            },
        )
        workspace.flags.ignore_permissions = True
        workspace.insert(ignore_permissions=True)
        frappe.db.commit()
        logger.info(f"Created workspace '{workspace_name}'")
        return True
    except Exception as e:
        logger.error(f"Error creating workspace: {str(e)}")
        frappe.log_error(
            f"Error creating workspace: {str(e)}\n{frappe.get_traceback()}",
            "Workspace Setup Error",
        )
        return False

def setup_default_modules() -> bool:
    try:
        logger.info("Setting up default modules")
        if not frappe.db.exists("DocType", "Module Def"):
            logger.warning("Module Def DocType does not exist")
            return False
        module_name = "Payroll Indonesia"
        if frappe.db.exists("Module Def", module_name):
            logger.info(f"Module '{module_name}' already exists")
            return True
        module = frappe.new_doc("Module Def")
        module.module_name = module_name
        module.app_name = "payroll_indonesia"
        module.custom = 0
        module.restricted = 0
        module.flags.ignore_permissions = True
        module.insert(ignore_permissions=True)
        frappe.db.commit()
        logger.info(f"Created module '{module_name}'")
        return True
    except Exception as e:
        logger.error(f"Error setting up default modules: {str(e)}")
        frappe.log_error(
            f"Error setting up default modules: {str(e)}\n{frappe.get_traceback()}",
            "Module Setup Error",
        )
        return False

def ensure_settings_doctype_exists() -> bool:
    try:
        logger.info("Ensuring Payroll Indonesia Settings exists")
        if not doctype_defined("Payroll Indonesia Settings"):
            logger.warning("Payroll Indonesia Settings DocType is not defined")
            return False
        
        # Load defaults from defaults.json
        app_path = frappe.get_app_path("payroll_indonesia")
        defaults_path = os.path.join(app_path, "defaults.json")
        defaults = {}
        if Path(defaults_path).exists():
            with open(defaults_path, 'r') as f:
                defaults = json.load(f)
        
        settings_name = "Payroll Indonesia Settings"
        if frappe.db.exists(settings_name, settings_name):
            logger.info("Payroll Indonesia Settings already exists")
            settings = frappe.get_doc(settings_name, settings_name)
        else:
            settings = frappe.new_doc(settings_name)
            settings.document_name = settings_name
            settings.enabled = 1
            settings.default_currency = "IDR"
            settings.max_working_days_per_month = 22
            settings.working_hours_per_day = 8.0
            settings.app_version = "1.0.0"
            settings.app_last_updated = now_datetime()
            try:
                settings.app_updated_by = frappe.session.user
            except (AttributeError, Exception):
                settings.app_updated_by = "Administrator"
        
        # Assign mandatory settings if missing, using defaults from defaults.json
        if not getattr(settings, "ptkp_table", None) and "ptkp" in defaults:
            if hasattr(settings, "ptkp_table"):
                # Handle child table
                settings.ptkp_table = []
                for status, value in defaults["ptkp"].items():
                    settings.append("ptkp_table", {
                        "ptkp_status": status,
                        "ptkp_value": value
                    })
            else:
                # Handle JSON field
                settings.ptkp_table = json.dumps(defaults.get("ptkp", {}))
        
        if not getattr(settings, "ptkp_ter_mapping_table", None) and "ptkp_to_ter_mapping" in defaults:
            if hasattr(settings, "ptkp_ter_mapping_table"):
                # Handle child table
                settings.ptkp_ter_mapping_table = []
                for ptkp_status, ter_category in defaults["ptkp_to_ter_mapping"].items():
                    settings.append("ptkp_ter_mapping_table", {
                        "ptkp_status": ptkp_status,
                        "ter_category": ter_category
                    })
            else:
                # Handle JSON field
                settings.ptkp_ter_mapping_table = json.dumps(defaults.get("ptkp_to_ter_mapping", {}))
        
        if not getattr(settings, "tax_bracket_table", None) and "tax_brackets" in defaults:
            if hasattr(settings, "tax_bracket_table"):
                # Handle child table
                settings.tax_bracket_table = []
                for bracket in defaults["tax_brackets"]:
                    settings.append("tax_bracket_table", {
                        "income_from": bracket.get("income_from", 0),
                        "income_to": bracket.get("income_to", 0),
                        "tax_rate": bracket.get("tax_rate", 0)
                    })
            else:
                # Handle JSON field
                settings.tax_bracket_table = json.dumps(defaults.get("tax_brackets", []))
        
        if not getattr(settings, "tipe_karyawan", None) and "tipe_karyawan" in defaults:
            if isinstance(defaults["tipe_karyawan"], list):
                # Handle child table or array field
                if hasattr(settings, "tipe_karyawan_table"):
                    settings.tipe_karyawan_table = []
                    for tipe in defaults["tipe_karyawan"]:
                        settings.append("tipe_karyawan_table", {
                            "tipe": tipe
                        })
                else:
                    # Handle JSON field
                    settings.tipe_karyawan = json.dumps(defaults.get("tipe_karyawan", []))
            else:
                # Handle simple field
                settings.tipe_karyawan = defaults.get("tipe_karyawan", "")
        
        # Fill in any additional default fields from tax section
        if "tax" in defaults:
            for key, val in defaults["tax"].items():
                if hasattr(settings, key) and not getattr(settings, key, None):
                    if isinstance(val, (dict, list)):
                        setattr(settings, key, json.dumps(val))
                    else:
                        setattr(settings, key, val)
        
        settings.flags.ignore_permissions = True
        if not frappe.db.exists(settings_name, settings_name):
            settings.insert(ignore_permissions=True)
        else:
            settings.save(ignore_permissions=True)
        
        frappe.db.commit()
        logger.info("Successfully created/updated Payroll Indonesia Settings")
        return True
    except Exception as e:
        logger.error(f"Error ensuring settings doctype exists: {str(e)}")
        frappe.log_error(
            f"Error ensuring settings doctype exists: {str(e)}\n{frappe.get_traceback()}",
            "Settings Setup Error",
        )
        return False

def after_sync() -> bool:
    try:
        logger.info("Synchronizing settings from defaults.json")
        app_path = frappe.get_app_path("payroll_indonesia")
        defaults_path = os.path.join(app_path, "defaults.json")
        if not Path(defaults_path).exists():
            logger.warning(f"defaults.json not found at {defaults_path}")
            return False
        with open(defaults_path, 'r') as f:
            defaults = json.load(f)
        if 'tax' not in defaults:
            logger.warning("Tax configuration not found in defaults.json")
            return False
        if not doctype_defined("Payroll Indonesia Settings"):
            logger.warning("Payroll Indonesia Settings DocType is not defined")
            return False
        if not frappe.db.table_exists("Payroll Indonesia Settings"):
            logger.warning("Payroll Indonesia Settings table does not exist in database")
            return False
        settings_name = "Payroll Indonesia Settings"
        if frappe.db.exists(settings_name, settings_name):
            settings = frappe.get_doc(settings_name, settings_name)
        else:
            settings = frappe.new_doc(settings_name)
            settings.document_name = settings_name
            settings.enabled = 1
        
        # Update settings from defaults.json
        for key, val in defaults["tax"].items():
            if hasattr(settings, key):
                setattr(settings, key, val)
        
        # Assign mandatory settings if missing, using defaults from defaults.json
        if not getattr(settings, "ptkp_table", None) and "ptkp" in defaults:
            if hasattr(settings, "ptkp_table"):
                # Handle child table
                settings.ptkp_table = []
                for status, value in defaults["ptkp"].items():
                    settings.append("ptkp_table", {
                        "ptkp_status": status,
                        "ptkp_value": value
                    })
            else:
                # Handle JSON field
                settings.ptkp_table = json.dumps(defaults.get("ptkp", {}))
        
        if not getattr(settings, "ptkp_ter_mapping_table", None) and "ptkp_to_ter_mapping" in defaults:
            if hasattr(settings, "ptkp_ter_mapping_table"):
                # Handle child table
                settings.ptkp_ter_mapping_table = []
                for ptkp_status, ter_category in defaults["ptkp_to_ter_mapping"].items():
                    settings.append("ptkp_ter_mapping_table", {
                        "ptkp_status": ptkp_status,
                        "ter_category": ter_category
                    })
            else:
                # Handle JSON field
                settings.ptkp_ter_mapping_table = json.dumps(defaults.get("ptkp_to_ter_mapping", {}))
        
        if not getattr(settings, "tax_bracket_table", None) and "tax_brackets" in defaults:
            if hasattr(settings, "tax_bracket_table"):
                # Handle child table
                settings.tax_bracket_table = []
                for bracket in defaults["tax_brackets"]:
                    settings.append("tax_bracket_table", {
                        "income_from": bracket.get("income_from", 0),
                        "income_to": bracket.get("income_to", 0),
                        "tax_rate": bracket.get("tax_rate", 0)
                    })
            else:
                # Handle JSON field
                settings.tax_bracket_table = json.dumps(defaults.get("tax_brackets", []))
        
        if not getattr(settings, "tipe_karyawan", None) and "tipe_karyawan" in defaults:
            if isinstance(defaults["tipe_karyawan"], list):
                # Handle child table or array field
                if hasattr(settings, "tipe_karyawan_table"):
                    settings.tipe_karyawan_table = []
                    for tipe in defaults["tipe_karyawan"]:
                        settings.append("tipe_karyawan_table", {
                            "tipe": tipe
                        })
                else:
                    # Handle JSON field
                    settings.tipe_karyawan = json.dumps(defaults.get("tipe_karyawan", []))
            else:
                # Handle simple field
                settings.tipe_karyawan = defaults.get("tipe_karyawan", "")
        
        settings.flags.ignore_permissions = True
        if not frappe.db.exists(settings_name, settings_name):
            settings.insert(ignore_permissions=True)
        else:
            settings.save(ignore_permissions=True)
            
        frappe.db.commit()
        _setup_field_aliases()
        logger.info("Successfully synchronized settings from defaults.json")
        return True
    except Exception as e:
        logger.error(f"Error synchronizing settings from defaults.json: {str(e)}")
        frappe.log_error(
            f"Error synchronizing settings: {str(e)}\n{frappe.get_traceback()}",
            "Settings Sync Error",
        )
        return False

def _setup_field_aliases() -> None:
    try:
        if not doctype_defined("Employee Tax Summary Monthly"):
            logger.info("Employee Tax Summary Monthly DocType not found, skipping field alias setup")
            return
        if not frappe.db.table_exists("Employee Tax Summary Monthly"):
            logger.info("Employee Tax Summary Monthly table does not exist, skipping field alias setup")
            return
        if not frappe.db.has_column("Employee Tax Summary Monthly", "tax_year"):
            frappe.make_property_setter({
                "doctype": "Employee Tax Summary Monthly",
                "field_name": "year",
                "property": "alias",
                "value": "tax_year",
                "property_type": "Data"
            })
            logger.info("Created field alias: 'tax_year' -> 'year' in Employee Tax Summary Monthly")
    except Exception as e:
        logger.warning(f"Error setting up field aliases: {str(e)}")