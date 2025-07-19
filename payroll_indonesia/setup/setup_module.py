# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
setup_module.py – basic setup routines for Payroll Indonesia.
Provides minimal setup functions used during installation and migration,
including helpers to map GL accounts to salary components.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime
from payroll_indonesia.config.config import doctype_defined
from payroll_indonesia.setup.settings_migration import migrate_all_settings, _load_defaults
from payroll_indonesia.frappe_helpers import get_logger

logger = get_logger("setup")


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

        # Load defaults from configuration
        defaults = _load_defaults()
        if not defaults:
            logger.warning("Could not load defaults from configuration")
            return False

        # Get all companies and create GL accounts
        companies = frappe.get_all("Company", pluck="name")
        for company in companies:
            setup_company_accounts(company=company, config=defaults)
        logger.info("Company accounts setup completed")

        logger.info("Setting up Payroll Indonesia tax infrastructure")

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


def ensure_bpjs_account_mappings(transaction_open=False) -> bool:
    """Ensure each company has a BPJS Account Mapping."""
    try:
        from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping import (
            create_default_mapping,
        )

        created = False
        companies = frappe.get_all("Company", pluck="name")
        for company in companies:
            if not frappe.db.exists("BPJS Account Mapping", {"company": company}):
                create_default_mapping(company)
                created = True

        return created
    except Exception as e:
        logger.error(f"Error ensuring BPJS Account Mappings: {str(e)}")
        return False


def after_migrate():
    """Run essential post-migration setup."""
    try:
        # Core setup that must always run
        ensure_settings_doctype_exists()

        # Delegate to fixtures.setup for the main installation
        from payroll_indonesia.fixtures.setup import perform_essential_setup
        perform_essential_setup()
        logger.info("Post-migration setup completed successfully")
    except Exception as e:
        logger.error(f"Error in after_migrate: {str(e)}")
