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
from pathlib import Path

import frappe
from frappe import _
from frappe.utils import now_datetime, cint, flt

from payroll_indonesia.frappe_helpers import get_logger
logger = get_logger("setup")

from payroll_indonesia.config.config import doctype_defined
from payroll_indonesia.setup.settings_migration import migrate_all_settings, _load_defaults

def setup_module() -> bool:
    """
    Primary setup function for Payroll Indonesia.
    Creates basic structure needed for the app to function.
    
    Returns:
        bool: Success status
    """
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
    """
    Setup tax infrastructure needed for Indonesian payroll.
    This is a facade function that delegates to appropriate setup functions.

    Returns:
        bool: Success status
    """
    try:
        from payroll_indonesia.fixtures.setup import setup_company_accounts

        # Get all companies
        companies = frappe.get_all("Company", pluck="name")
        for company in companies:
            setup_company_accounts(None, company=company)
        logger.info("Company accounts setup completed")

        logger.info("Setting up Payroll Indonesia tax infrastructure")

        # Load defaults from configuration
        defaults = _load_defaults()
        if not defaults:
            logger.warning("Could not load defaults from configuration")
            return False

        # Import specialized setup functions
        from payroll_indonesia.utilities.tax_slab import setup_income_tax_slab
        from payroll_indonesia.fixtures.setup import setup_pph21_ter

        results = {"income_tax_slab": False, "pph21_ter": False}

        # Setup income tax slab if needed
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

        # Let fixtures.setup handle TER setup since it's more specialized
        try:
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
    except Exception as e:
        logger.error(f"Error setting up accounts: {str(e)}")
        return False

def create_custom_workspace() -> bool:
    """
    Create the Payroll Indonesia workspace.
    
    Returns:
        bool: Success status
    """
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
    """
    Create the Payroll Indonesia module definition.
    
    Returns:
        bool: Success status
    """
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
    """
    Create the Payroll Indonesia Settings document if it doesn't exist.
    Only creates the basic document structure with minimal required fields.
    Data population is delegated to settings_migration.py.
    
    Returns:
        bool: Success status
    """
    try:
        logger.info("Ensuring Payroll Indonesia Settings exists")
        if not doctype_defined("Payroll Indonesia Settings"):
            logger.warning("Payroll Indonesia Settings DocType is not defined")
            return False
        
        settings_name = "Payroll Indonesia Settings"
        if frappe.db.exists(settings_name, settings_name):
            logger.info("Payroll Indonesia Settings already exists")
            return True

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

        settings.flags.ignore_permissions = True
        settings.flags.ignore_mandatory = True
        settings.insert(ignore_permissions=True)
        frappe.db.commit()

        logger.info("Running settings migration for the new settings document")
        defaults = _load_defaults()
        if defaults:
            migrate_all_settings(settings_doc=settings, defaults=defaults)

        logger.info("Successfully created Payroll Indonesia Settings")
        return True
    except Exception as e:
        logger.error(f"Error ensuring settings doctype exists: {str(e)}")
        frappe.log_error(
            f"Error ensuring settings doctype exists: {str(e)}\n{frappe.get_traceback()}",
            "Settings Setup Error",
        )
        return False

def after_sync() -> bool:
    """
    Hook called after app code is synchronized.
    Updates settings from defaults.json.
    
    Returns:
        bool: Success status
    """
    try:
        logger.info("Synchronizing settings from defaults.json")

        if not doctype_defined("Payroll Indonesia Settings"):
            logger.warning("Payroll Indonesia Settings DocType is not defined")
            return False

        if not frappe.db.table_exists("Payroll Indonesia Settings"):
            logger.warning("Payroll Indonesia Settings table does not exist in database")
            return False

        defaults = _load_defaults()
        if not defaults:
            logger.warning("Could not load defaults from configuration")
            return False

        settings_name = "Payroll Indonesia Settings"
        if frappe.db.exists(settings_name, settings_name):
            settings = frappe.get_doc(settings_name, settings_name)
        else:
            return ensure_settings_doctype_exists()

        results = migrate_all_settings(settings_doc=settings, defaults=defaults)

        _setup_field_aliases()

        success_count = sum(1 for result in results.values() if result)
        total_count = len(results)
        logger.info(f"Settings sync summary: {success_count}/{total_count} sections updated")

        # Install custom fields programmatically
        from payroll_indonesia.setup.install_custom_fields import install_custom_fields
        install_custom_fields()
        logger.info("Custom fields installed successfully after sync")

        return True
    except Exception as e:
        logger.error(f"Error synchronizing settings from defaults.json: {str(e)}")
        frappe.log_error(
            f"Error synchronizing settings: {str(e)}\n{frappe.get_traceback()}",
            "Settings Sync Error",
        )
        return False

def _setup_field_aliases() -> None:
    """
    Set up field aliases for various doctypes.
    """
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

def after_migrate():
    """Run after migrate"""
    try:
        # Setup fixtures that may have been skipped
        setup_accounts()

        # Setup default salary structure
        from payroll_indonesia.fixtures.setup import setup_default_salary_structure
        setup_default_salary_structure()

        logger.info("Post-migration setup completed successfully")
    except Exception as e:
        logger.error(f"Error in after_migrate: {str(e)}")
