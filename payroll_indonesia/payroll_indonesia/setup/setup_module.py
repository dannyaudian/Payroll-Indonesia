# -*- coding: utf-8 -*-
"""setup_module.py – consolidated post‑migration setup
This file contains utilities for Payroll Indonesia setup.
It is hooked via **after_migrate** in hooks.py.
"""

from __future__ import unicode_literals

import frappe

# from frappe.utils import cint

# ---------------------------------------------------------------------------
# Central utilities
# ---------------------------------------------------------------------------
from payroll_indonesia.payroll_indonesia.utils import debug_log

# ---------------------------------------------------------------------------
# Public hook functions
# ---------------------------------------------------------------------------


def after_sync():
    """Public hook called after app sync/migrate."""
    debug_log("Running after_sync for Payroll Indonesia", "Setup")

    # Ensure Payroll Indonesia Settings exists
    ensure_payroll_indonesia_settings()

    # Ensure BPJS Account Mapping exists for all companies
    create_bpjs_account_mappings_for_companies()


def after_install():
    """Hook called after app installation."""
    debug_log("Running after_install setup for Payroll Indonesia", "Setup")

    # Ensure Payroll Indonesia Settings exists
    ensure_payroll_indonesia_settings()

    # Ensure BPJS Account Mapping exists for all companies
    create_bpjs_account_mappings_for_companies()


# ---------------------------------------------------------------------------
# Settings setup functions
# ---------------------------------------------------------------------------


def ensure_payroll_indonesia_settings():
    """
    Ensure a single "Payroll Indonesia Settings" document exists

    Creates the settings document if it doesn't exist yet
    """
    debug_log("Checking if Payroll Indonesia Settings exists", "Setup")

    if not frappe.db.exists("Payroll Indonesia Settings", "Payroll Indonesia Settings"):
        try:
            debug_log("Creating Payroll Indonesia Settings", "Setup")

            # Create settings document
            settings = frappe.new_doc("Payroll Indonesia Settings")
            settings.document_name = "Payroll Indonesia Settings"

            # Set default values if needed
            settings.enabled = 1
            settings.auto_create_salary_structure = 1

            # Insert with ignore_permissions
            settings.flags.ignore_permissions = True
            settings.insert(ignore_permissions=True)

            # Commit changes
            frappe.db.commit()

            debug_log("Successfully created Payroll Indonesia Settings", "Setup")

        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(f"Error creating Payroll Indonesia Settings: {str(e)}", "Setup Error")
            debug_log(
                f"Error creating Payroll Indonesia Settings: {str(e)}", "Setup Error", trace=True
            )
    else:
        debug_log("Payroll Indonesia Settings already exists", "Setup")


def create_bpjs_account_mappings_for_companies():
    """
    Create BPJS Account Mapping for all companies if they don't exist

    This function:
    1. Gets all active companies
    2. Checks if BPJS Account Mapping exists for each company
    3. Creates a default mapping if it doesn't exist
    """
    debug_log("Starting BPJS Account Mapping setup for companies", "Setup")

    try:
        # Get all active companies
        companies = frappe.get_all("Company", filters={"is_group": 0, "disabled": 0}, pluck="name")

        if not companies:
            debug_log("No active companies found", "Setup")
            return

        # Track statistics for logging
        created_count = 0
        skipped_count = 0

        # Check and create mapping for each company
        for company in companies:
            if frappe.db.exists("BPJS Account Mapping", {"company": company}):
                debug_log(f"BPJS Account Mapping already exists for company: {company}", "Setup")
                skipped_count += 1
            else:
                create_default_mapping(company)
                created_count += 1

        # Log summary
        debug_log(
            f"BPJS Account Mapping creation summary: created={created_count}, skipped={skipped_count}",
            "Setup",
        )

    except Exception as e:
        frappe.log_error(f"Error setting up BPJS Account Mappings: {str(e)}", "Setup Error")
        debug_log(f"Error setting up BPJS Account Mappings: {str(e)}", "Setup Error", trace=True)


def create_default_mapping(company):
    """
    Create a default BPJS Account Mapping for a specific company

    Args:
        company (str): Name of the company

    Returns:
        object: The created BPJS Account Mapping document
    """
    debug_log(f"Creating default BPJS Account Mapping for company: {company}", "Setup")

    try:
        # Create the mapping document
        mapping = frappe.new_doc("BPJS Account Mapping")
        mapping.company = company
        mapping.mapping_name = f"BPJS Mapping - {company}"

        # Set blank accounts as required
        mapping.bpjs_kesehatan_employee_account = ""
        mapping.bpjs_kesehatan_employer_account = ""
        mapping.bpjs_ketenagakerjaan_jht_employee_account = ""
        mapping.bpjs_ketenagakerjaan_jht_employer_account = ""
        mapping.bpjs_ketenagakerjaan_jp_employee_account = ""
        mapping.bpjs_ketenagakerjaan_jp_employer_account = ""
        mapping.bpjs_ketenagakerjaan_jkk_account = ""
        mapping.bpjs_ketenagakerjaan_jkm_account = ""

        # Default payable accounts
        mapping.bpjs_kesehatan_payable_account = ""
        mapping.bpjs_ketenagakerjaan_payable_account = ""

        # Default cost centers
        mapping.default_cost_center = ""

        # Insert with ignore_permissions
        mapping.flags.ignore_permissions = True
        mapping.insert(ignore_permissions=True)

        debug_log(f"Successfully created default BPJS Account Mapping for {company}", "Setup")

        return mapping

    except Exception as e:
        frappe.log_error(
            f"Error creating default BPJS Account Mapping for {company}: {str(e)}", "Setup Error"
        )
        debug_log(
            f"Error creating default BPJS Account Mapping for {company}: {str(e)}",
            "Setup Error",
            trace=True,
        )
        return None
