# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
setup_module.py – basic setup routines for Payroll Indonesia.
Provides minimal setup functions used during installation and migration.
"""

from typing import Dict, Any, Optional, List

import frappe
from frappe import _
from frappe.utils import now_datetime

from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.utilities.tax_slab import setup_income_tax_slab
from payroll_indonesia.setup.settings_migration import _load_defaults


def setup_module() -> bool:
    """
    Main entry point for basic Payroll Indonesia setup routines.
    Called during post-install.

    Returns:
        bool: Success status of setup operations
    """
    logger.info("Starting Payroll Indonesia basic setup")

    # Run basic setup functions in sequence
    results = [
        create_custom_workspace(),
        setup_default_modules(),
        ensure_settings_doctype_exists(),
    ]

    # Check if all setup functions succeeded
    success = all(results)

    if success:
        logger.info("Payroll Indonesia basic setup completed successfully")
    else:
        logger.warning("Payroll Indonesia basic setup completed with warnings")

    return success


def setup_accounts() -> bool:
    """
    Setup accounts and ensure Income Tax Slab and TER rates exist.
    This function can safely be hooked into after_migrate.
    
    Returns:
        bool: Success status of setup operations
    """
    logger.info("Setting up Payroll Indonesia tax infrastructure")
    
    results = {
        "income_tax_slab": False,
        "pph21_ter": False
    }
    
    # Get defaults from Frappe system defaults
    try:
        defaults = frappe.defaults.get_defaults()
        logger.info("Obtained system defaults for tax setup")
    except Exception as e:
        logger.warning(f"Could not get system defaults, falling back to config: {str(e)}")
        defaults = {}
    
    # Supplement with app-specific defaults if needed
    config_defaults = _load_defaults()
    if config_defaults:
        # Merge defaults, giving priority to system defaults
        for key, value in config_defaults.items():
            if key not in defaults:
                defaults[key] = value
    
    # Setup Income Tax Slab with new signature
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
    
    # Setup PPh 21 TER rates
    try:
        # Import here to avoid circular imports
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
    
    # Overall success if at least one component was successful
    success = any(results.values())
    
    if success:
        logger.info("Payroll Indonesia tax infrastructure setup completed")
    else:
        logger.warning("Payroll Indonesia tax infrastructure setup completed with warnings")
    
    return success


def create_custom_workspace() -> bool:
    """
    Create or update Payroll Indonesia custom workspace.

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info("Setting up Payroll Indonesia workspace")

        # Check if workspace DocType exists
        if not frappe.db.table_exists("Workspace"):
            logger.warning("Workspace DocType does not exist")
            return False

        workspace_name = "Payroll Indonesia"

        # Check if workspace already exists
        if frappe.db.exists("Workspace", workspace_name):
            logger.info(f"Workspace '{workspace_name}' already exists")
            return True

        # Create new workspace
        workspace = frappe.new_doc("Workspace")
        workspace.name = workspace_name
        workspace.label = workspace_name
        workspace.category = "Modules"
        workspace.icon = "payroll"
        workspace.module = "Payroll Indonesia"
        workspace.onboarding = "Payroll Indonesia"
        workspace.is_hidden = 0
        workspace.for_user = ""

        # Add links to the workspace
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

        # Save with ignore_permissions
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
    Set up default modules required for Payroll Indonesia.

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info("Setting up default modules")

        # Check if Module Def DocType exists
        if not frappe.db.table_exists("Module Def"):
            logger.warning("Module Def DocType does not exist")
            return False

        module_name = "Payroll Indonesia"

        # Check if module already exists
        if frappe.db.exists("Module Def", module_name):
            logger.info(f"Module '{module_name}' already exists")
            return True

        # Create new module
        module = frappe.new_doc("Module Def")
        module.module_name = module_name
        module.app_name = "payroll_indonesia"
        module.custom = 0
        module.restricted = 0

        # Save with ignore_permissions
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
    Ensure Payroll Indonesia Settings document exists with basic defaults.

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info("Ensuring Payroll Indonesia Settings exists")

        # Check if DocType exists
        if not frappe.db.table_exists("Payroll Indonesia Settings"):
            logger.warning("Payroll Indonesia Settings DocType does not exist")
            return False

        settings_name = "Payroll Indonesia Settings"

        # Check if settings already exist
        if frappe.db.exists(settings_name, settings_name):
            logger.info("Payroll Indonesia Settings already exists")
            return True

        # Create new settings
        settings = frappe.new_doc(settings_name)
        settings.document_name = settings_name
        settings.enabled = 1

        # Set default values
        settings.default_currency = "IDR"
        settings.max_working_days_per_month = 22
        settings.working_hours_per_day = 8.0

        # Set app info
        settings.app_version = "1.0.0"
        settings.app_last_updated = now_datetime()

        # Use Administrator if session user is not available
        try:
            settings.app_updated_by = frappe.session.user
        except (AttributeError, Exception):
            settings.app_updated_by = "Administrator"

        # Save with ignore_permissions
        settings.flags.ignore_permissions = True
        settings.insert(ignore_permissions=True)
        frappe.db.commit()

        logger.info("Successfully created Payroll Indonesia Settings")
        return True

    except Exception as e:
        logger.error(f"Error ensuring settings doctype exists: {str(e)}")
        frappe.log_error(
            f"Error ensuring settings doctype exists: {str(e)}\n{frappe.get_traceback()}",
            "Settings Setup Error",
        )
        return False