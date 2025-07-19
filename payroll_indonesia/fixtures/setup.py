# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 12:12:46 by dannyaudian

"""
Setup module for Payroll Indonesia.

Handles installation, sync, and system configuration for Indonesian payroll.
"""

import json
from pathlib import Path

import frappe
from frappe import _
from frappe.exceptions import ValidationError
from frappe.utils import getdate, flt, cint

from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.override import salary_structure
from payroll_indonesia.config.config import get_config as get_default_config
from payroll_indonesia.config.config import doctype_defined, get_tax_effect_types
from payroll_indonesia.config.gl_account_mapper import (
    get_gl_account_for_salary_component,
    map_gl_account,
    _map_component_to_account,
)
from payroll_indonesia.setup.settings_migration import migrate_all_settings, _load_defaults
from payroll_indonesia.setup.setup_module import ensure_bpjs_account_mappings


# Define exported functions
__all__ = [
    "before_install",
    "after_install",
    "after_sync",
    "check_system_readiness",
    "setup_accounts",
    "create_supplier_group",
    "create_bpjs_supplier",
    "setup_salary_components",
    "setup_default_salary_structure",
    "display_installation_summary",
    "setup_pph21_ter",
    "setup_income_tax_slab",
]


def _run_full_install(config=None, skip_existing=True):
    """
    Centralized function to run the full installation process.
    Creates all required records and configurations.

    Args:
        config: Configuration dictionary (optional, loaded from defaults if None)
        skip_existing: Whether to skip creation of components that already exist

    Returns:
        dict: Results of installation steps
    """
    if config is None:
        config = get_default_config()

    results = {
        "accounts": False,
        "suppliers": False,
        "settings": False,
        "salary_components": False,
        "salary_structure": False,
    }

    try:
        # Create a transaction to ensure all or nothing
        frappe.db.begin()

        # Setup accounts
        results["accounts"] = setup_accounts(config)
        ensure_bpjs_account_mappings()
        logger.info("Account setup completed")

        # Setup suppliers
        suppliers_ok = create_supplier_group()
        if suppliers_ok and config.get("suppliers", {}).get("bpjs", {}):
            suppliers_ok = create_bpjs_supplier(config)
        results["suppliers"] = suppliers_ok
        logger.info("Supplier setup completed")

        # Create and populate Payroll Indonesia Settings
        results["settings"] = setup_payroll_settings()
        logger.info("Payroll Indonesia Settings setup completed")

        # Setup salary components
        results["salary_components"] = setup_salary_components(config)
        logger.info("Salary components setup completed")

        # Setup default salary structure
        results["salary_structure"] = setup_default_salary_structure()
        logger.info("Default salary structure setup completed")

        # Setup TER rates if needed and tax calculation method is TER
        try:
            settings_doc = frappe.get_single("Payroll Indonesia Settings")
            if settings_doc.tax_calculation_method == "TER" and not frappe.db.exists(
                "PPh 21 TER Table", {"status_pajak": ["in", ["TER A", "TER B", "TER C"]]}
            ):
                setup_pph21_ter(config)
        except Exception as e:
            logger.warning(f"Error setting up TER rates: {str(e)}")

        # Setup income tax slab if needed
        try:
            if not frappe.db.exists("Income Tax Slab", {"currency": "IDR", "is_default": 1}):
                setup_income_tax_slab(config)
        except Exception as e:
            logger.warning(f"Error setting up income tax slab: {str(e)}")

        # Commit all changes at once
        frappe.db.commit()
        logger.info("All changes committed successfully")

    except Exception as e:
        frappe.db.rollback()
        logger.error(f"Installation failed, rolling back: {str(e)}")
        raise

    display_installation_summary(results, config)
    return results


def after_install():
    """
    Main after_install hook for the Payroll Indonesia app.
    Runs all setup steps in sequence and logs results.

    This is automatically called by Frappe after app installation.
    """
    logger.info("Starting Payroll Indonesia after_install process")

    try:
        _run_full_install()
    except Exception as e:
        logger.error(f"Error during installation: {str(e)}", exc_info=True)
        frappe.log_error(
            f"Error during installation: {str(e)}\n\n{frappe.get_traceback()}",
            "Installation Error",
        )


def after_sync():
    """
    Hook after app sync. Ensures Payroll Indonesia Settings exists and is populated.

    This function ensures all configuration data from defaults.json is properly
    migrated to Payroll Indonesia Settings and its child tables.

    Returns:
        None
    """
    logger.info("Starting after_sync process for Payroll Indonesia")

    # Check if function already ran in this session (idempotent)
    if hasattr(after_sync, "already_run") and after_sync.already_run:
        logger.info("after_sync already ran in this session, skipping")
        return

    try:
        # Begin transaction
        frappe.db.begin()

        # Load defaults from settings_migration
        defaults = _load_defaults()
        if not defaults:
            logger.warning("Failed to load configuration from defaults.json")
            return

        # Run migration with zero args - it will automatically load the settings doc
        logger.info("Running migrate_all_settings()")
        results = migrate_all_settings()

        # Log summary of results
        if results:
            success_count = sum(1 for result in results.values() if result)
            total_count = len(results)
            logger.info(
                f"Settings migration results: {success_count}/{total_count} sections updated"
            )

            # Log individual results for debugging
            for section, success in results.items():
                status = "updated" if success else "skipped"
                logger.debug(f"Section '{section}': {status}")
        else:
            logger.warning("migrate_all_settings() returned no results")

        # Run simplified installation to ensure components exist
        try:
            _run_full_install(defaults, skip_existing=True)
        except Exception as e:
            logger.error(f"Error during full install: {str(e)}")

        # Commit changes
        frappe.db.commit()
        logger.info("after_sync process completed successfully")

        # Mark as run for idempotence
        after_sync.already_run = True

    except Exception as e:
        frappe.db.rollback()
        logger.error(f"Error during after_sync: {str(e)}", exc_info=True)
        frappe.log_error(
            f"Error during after_sync: {str(e)}\n\n{frappe.get_traceback()}",
            "Payroll Indonesia Sync Error",
        )


def before_install():
    """Run system checks before installation."""
    try:
        check_system_readiness()
    except Exception as e:
        frappe.log_error(
            f"Error during before_install: {str(e)}\n\n{frappe.get_traceback()}",
            "Payroll Indonesia Installation Error",
        )
        frappe.log("Error during before_install: {str(e)}")


def check_system_readiness():
    """
    Checks if required DocTypes and tables exist.

    Returns:
        bool: True if system is ready, False otherwise
    """
    required_core_doctypes = [
        "Salary Component",
        "Salary Structure",
        "Salary Slip",
        "Employee",
        "Company",
        "Account",
    ]
    missing_doctypes = []
    for doctype in required_core_doctypes:
        if not frappe.db.table_exists(doctype):
            missing_doctypes.append(doctype)

    if missing_doctypes:
        logger.warning(f"Required tables missing: {', '.join(missing_doctypes)}")
        frappe.log_error(
            f"Required tables missing: {', '.join(missing_doctypes)}", "System Readiness Check"
        )

    company_records = frappe.get_all("Company") if frappe.db.table_exists("Company") else []
    if not company_records:
        logger.warning("No company found. Some setup steps may fail.")
        frappe.log_error("No company found", "System Readiness Check")

    return True


def setup_payroll_settings():
    """
    Setup Payroll Indonesia Settings with default values.

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Ensure the settings document exists
        if not doctype_defined("Payroll Indonesia Settings"):
            logger.warning("Payroll Indonesia Settings doctype not found")
            return False

        if not frappe.db.exists("Payroll Indonesia Settings", "Payroll Indonesia Settings"):
            logger.info("Creating new Payroll Indonesia Settings document")
            settings_doc = frappe.new_doc("Payroll Indonesia Settings")
            settings_doc.enabled = 1
            settings_doc.app_version = "1.0.0"
            settings_doc.app_last_updated = frappe.utils.now()
            settings_doc.app_updated_by = frappe.session.user or "Administrator"

            settings_doc.flags.ignore_permissions = True
            settings_doc.flags.ignore_validate = True
            settings_doc.flags.ignore_mandatory = True
            settings_doc.insert(ignore_permissions=True)

            logger.info("Created new Payroll Indonesia Settings document")

        # Run migration with zero args
        results = migrate_all_settings()

        logger.info("Payroll Indonesia Settings configured successfully")
        return True

    except Exception as e:
        logger.error(f"Error setting up Payroll Indonesia Settings: {str(e)}")
        raise


def setup_accounts(config=None, specific_company=None):
    """
    Set up GL accounts for Indonesian payroll from config.

    Args:
        config: Configuration dictionary from defaults.json
        specific_company: Specific company to set up accounts for

    Returns:
        dict: Results of account setup
    """
    if not frappe.db.table_exists("Account"):
        logger.warning("Account table does not exist")
        return False

    if config is None:
        config = get_default_config()

    # Import helper functions
    from payroll_indonesia.payroll_indonesia.utils import (
        get_or_create_account,
        find_parent_account,
        create_parent_liability_account,
        create_parent_expense_account,
    )

    results = {"success": True, "created": [], "skipped": [], "errors": []}
    companies = []

    if specific_company:
        if frappe.db.table_exists("Company"):
            companies = frappe.get_all(
                "Company", filters={"name": specific_company}, fields=["name", "abbr"]
            )
            logger.info(f"Setting up accounts for specific company: {specific_company}")
    else:
        if frappe.db.table_exists("Company"):
            companies = frappe.get_all("Company", fields=["name", "abbr"])
            logger.info(f"Setting up accounts for all companies: {len(companies)} found")

    if not companies:
        logger.warning("No companies found for account setup")
        results["success"] = False
        results["errors"].append("No companies found")
        return results

    for company in companies:
        try:
            # Create parent accounts
            liability_parent = create_parent_liability_account(company.name)
            expense_parent = create_parent_expense_account(company.name)

            # Create tax payable account
            tax_payable = get_or_create_account(
                company=company.name,
                account_name="PPh 21 Payable",
                account_type="Tax",
                is_group=0,
                root_type="Liability",
            )

            # Create BPJS accounts (just a few key ones for demonstration)
            bpjs_accounts = [
                ("BPJS Kesehatan Payable", "Tax", "Liability"),
                ("BPJS JHT Payable", "Tax", "Liability"),
                ("BPJS JP Payable", "Tax", "Liability"),
                ("BPJS JKK Payable", "Tax", "Liability"),
                ("BPJS JKM Payable", "Tax", "Liability"),
                ("BPJS Kesehatan Expense", "Expense Account", "Expense"),
                ("BPJS JHT Expense", "Expense Account", "Expense"),
                ("BPJS JP Expense", "Expense Account", "Expense"),
                ("BPJS JKK Expense", "Expense Account", "Expense"),
                ("BPJS JKM Expense", "Expense Account", "Expense"),
            ]

            for account_name, account_type, root_type in bpjs_accounts:
                get_or_create_account(
                    company=company.name,
                    account_name=account_name,
                    account_type=account_type,
                    is_group=0,
                    root_type=root_type,
                )

            results["created"].append(company.name)

        except Exception as e:
            results["success"] = False
            results["errors"].append(f"Error setting up accounts for {company.name}: {str(e)}")
            logger.error(f"Error setting up accounts for {company.name}: {str(e)}")

    logger.info(
        f"Account setup completed: {len(results['created'])} created, {len(results['skipped'])} skipped, {len(results['errors'])} errors"
    )

    return results


def create_supplier_group():
    """
    Create Government supplier group for tax and BPJS entities.

    Returns:
        bool: True if successful, False otherwise
    """
    if not frappe.db.table_exists("Supplier Group"):
        logger.warning("Supplier Group table does not exist")
        return False

    try:
        if frappe.db.exists("Supplier Group", "Government"):
            logger.info("Government supplier group already exists")
            return True

        if not frappe.db.exists("Supplier Group", "All Supplier Groups"):
            logger.warning("All Supplier Groups parent group missing")
            return False

        group = frappe.new_doc("Supplier Group")
        group.supplier_group_name = "Government"
        group.parent_supplier_group = "All Supplier Groups"
        group.is_group = 0
        group.flags.ignore_permissions = True
        group.insert(ignore_permissions=True)

        for subgroup in ["BPJS Provider", "Tax Authority"]:
            if not frappe.db.exists("Supplier Group", subgroup):
                sg = frappe.new_doc("Supplier Group")
                sg.supplier_group_name = subgroup
                sg.parent_supplier_group = "Government"
                sg.is_group = 0
                sg.flags.ignore_permissions = True
                sg.insert(ignore_permissions=True)
                logger.info(f"Created {subgroup} supplier group")

        logger.info("Created Government supplier group hierarchy")
        return True

    except Exception as e:
        logger.error(f"Failed to create supplier group: {str(e)}")
        raise


def create_bpjs_supplier(config):
    """
    Create BPJS supplier entity from config.

    Args:
        config: Configuration dictionary from defaults.json

    Returns:
        bool: True if successful, False otherwise
    """
    if not frappe.db.table_exists("Supplier"):
        logger.warning("Supplier table does not exist")
        return False

    try:
        supplier_config = config.get("suppliers", {}).get("bpjs", {})
        if not supplier_config:
            logger.warning("No BPJS supplier configuration found")
            return False

        supplier_name = supplier_config.get("supplier_name", "BPJS")
        if frappe.db.exists("Supplier", supplier_name):
            logger.info(f"Supplier {supplier_name} already exists")
            return True

        supplier_group = supplier_config.get("supplier_group", "Government")
        if not frappe.db.exists("Supplier Group", supplier_group):
            supplier_group = (
                "BPJS Provider"
                if frappe.db.exists("Supplier Group", "BPJS Provider")
                else "Government"
            )
            if not frappe.db.exists("Supplier Group", supplier_group):
                logger.warning("No suitable supplier group exists")
                return False

        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = supplier_name
        supplier.supplier_group = supplier_group
        supplier.supplier_type = supplier_config.get("supplier_type", "Government")
        supplier.country = supplier_config.get("country", "Indonesia")
        supplier.default_currency = supplier_config.get("default_currency", "IDR")
        supplier.flags.ignore_permissions = True
        supplier.insert(ignore_permissions=True)

        logger.info(f"Created supplier: {supplier_name}")
        return True

    except Exception as e:
        logger.error(f"Failed to create BPJS supplier: {str(e)}")
        raise


def setup_pph21_ter(defaults=None):
    """
    Setup PPh 21 TER rates and other required tables in Payroll Indonesia Settings.

    Args:
        defaults: Configuration data, loaded from defaults.json if None

    Returns:
        bool: True if setup was successful, False otherwise
    """
    try:
        # Load defaults if not provided
        if defaults is None:
            from payroll_indonesia.setup.settings_migration import _load_defaults

            defaults = _load_defaults()
            if not defaults:
                logger.warning("Could not load defaults for PPh 21 TER setup")
                return False

        settings = frappe.get_single("Payroll Indonesia Settings")

        # Check if all required tables already have data
        tables_filled = (
            settings.ter_rate_table
            and settings.ptkp_table
            and settings.ptkp_ter_mapping_table
            and settings.tax_brackets_table
            and settings.tipe_karyawan
        )

        if tables_filled:
            logger.info("All required tables already have data in Payroll Indonesia Settings")
            return True

        # PTKP Table
        if not settings.ptkp_table:
            settings.set("ptkp_table", [])
            ptkp_values = defaults.get("ptkp", {})
            if isinstance(ptkp_values, dict):
                for status, amount in ptkp_values.items():
                    settings.append(
                        "ptkp_table", {"status_pajak": status, "ptkp_amount": flt(amount)}
                    )
            logger.info(f"Added {len(ptkp_values)} PTKP values")

        # PTKP TER Mapping Table
        if not settings.ptkp_ter_mapping_table:
            settings.set("ptkp_ter_mapping_table", [])
            mapping = defaults.get("ptkp_to_ter_mapping", {})
            if isinstance(mapping, dict):
                for ptkp_status, ter_category in mapping.items():
                    settings.append(
                        "ptkp_ter_mapping_table",
                        {"ptkp_status": ptkp_status, "ter_category": ter_category},
                    )
            logger.info(f"Added {len(mapping)} PTKP-TER mappings")

        # Tax Brackets Table
        if not settings.tax_brackets_table:
            settings.set("tax_brackets_table", [])
            brackets = defaults.get("tax_brackets", [])
            for bracket in brackets:
                settings.append(
                    "tax_brackets_table",
                    {
                        "income_from": flt(bracket.get("income_from", 0)),
                        "income_to": flt(bracket.get("income_to", 0)),
                        "tax_rate": flt(bracket.get("tax_rate", 0)),
                    },
                )
            logger.info(f"Added {len(brackets)} tax brackets")

        # Tipe Karyawan
        if not settings.tipe_karyawan:
            settings.set("tipe_karyawan", [])
            tipe_karyawan = defaults.get("tipe_karyawan", ["Tetap", "Tidak Tetap", "Freelance"])
            if isinstance(tipe_karyawan, list):
                for tipe in tipe_karyawan:
                    if isinstance(tipe, str):
                        settings.append("tipe_karyawan", {"tipe_karyawan": tipe})
                    elif isinstance(tipe, dict) and "tipe_karyawan" in tipe:
                        settings.append("tipe_karyawan", tipe)
            logger.info(f"Added {len(tipe_karyawan)} employee types")

        # TER Rates Table
        if not settings.ter_rate_table:
            # Get TER rates from defaults
            ter_rates = defaults.get("ter_rates", {})

            # Set metadata if available
            metadata = ter_rates.get("metadata", {})
            if metadata:
                for field, value in metadata.items():
                    field_name = f"ter_{field}"
                    if hasattr(settings, field_name):
                        setattr(settings, field_name, value)

            # Prepare TER rate table rows
            settings.set("ter_rate_table", [])
            count = 0

            # Convert dict structure to list of rows
            for category, rates in ter_rates.items():
                # Skip metadata
                if category == "metadata":
                    continue

                # Process each rate in this category
                for rate_data in rates:
                    # Create a new row with all needed fields
                    row = {
                        "status_pajak": category,
                        "income_from": flt(rate_data.get("income_from", 0)),
                        "income_to": flt(rate_data.get("income_to", 0)),
                        "rate": flt(rate_data.get("rate", 0)),
                        "is_highest_bracket": cint(rate_data.get("is_highest_bracket", 0)),
                    }
                    settings.append("ter_rate_table", row)
                    count += 1

            logger.info(f"Added {count} TER rate rows")

        # Save settings
        settings.flags.ignore_permissions = True
        settings.save(ignore_permissions=True)
        frappe.db.commit()

        logger.info("All required tables in Payroll Indonesia Settings populated successfully")
        return True

    except Exception as e:
        logger.error(f"Error in setup_pph21_ter: {str(e)}")
        # Shorter error message to avoid truncation
        frappe.log_error(
            "Error setting up required tables in Payroll Indonesia Settings", "Setup Error"
        )
        return False


def setup_income_tax_slab(config, force_update=False):
    """
    Create Income Tax Slab for Indonesia using config data.

    Args:
        config: Configuration dictionary from defaults.json
        force_update: Update existing record if it already exists

    Returns:
        bool: True if successful, False otherwise
    """
    if not frappe.db.table_exists("Income Tax Slab"):
        logger.warning("Income Tax Slab table does not exist")
        return False

    try:
        slab_name = "Indonesia Income Tax"
        slab_exists = frappe.db.exists("Income Tax Slab", slab_name)
        if slab_exists and not force_update:
            logger.info("Income Tax Slab already exists")
            return True

        company = frappe.db.get_default("company")
        if not company and frappe.db.table_exists("Company"):
            companies = frappe.get_all("Company", pluck="name")
            company = companies[0] if companies else None

        if not company:
            logger.warning("No company found for income tax slab")
            return False

        tax_brackets = config.get("tax_brackets", [])
        if not tax_brackets:
            logger.warning("No tax brackets found in configuration")
            raise ValidationError("No tax brackets found in configuration")

        if slab_exists:
            tax_slab = frappe.get_doc("Income Tax Slab", slab_name)
            tax_slab.slabs = []
        else:
            tax_slab = frappe.new_doc("Income Tax Slab")
            tax_slab.name = slab_name
            tax_slab.title = slab_name
        tax_slab.effective_from = getdate("2023-01-01")
        tax_slab.company = company
        tax_slab.currency = config.get("defaults", {}).get("currency", "IDR")
        tax_slab.is_default = 1
        tax_slab.disabled = 0

        for bracket in tax_brackets:
            tax_slab.append(
                "slabs",
                {
                    "from_amount": flt(bracket["income_from"]),
                    "to_amount": flt(bracket["income_to"]),
                    "percent_deduction": flt(bracket["tax_rate"]),
                },
            )

        tax_slab.flags.ignore_permissions = True
        tax_slab.flags.ignore_mandatory = True
        if slab_exists:
            tax_slab.save(ignore_permissions=True)
            logger.info(f"Updated income tax slab: {tax_slab.name}")
        else:
            tax_slab.insert()
            logger.info(f"Created income tax slab: {tax_slab.name}")
        return True

    except Exception as e:
        logger.error(f"Error creating or updating income tax slab: {str(e)}")
        raise


def setup_salary_components(config):
    """
    Create or update salary components using config data.

    Args:
        config: Configuration dictionary from defaults.json

    Returns:
        bool: True if successful, False otherwise
    """
    if not frappe.db.table_exists("Salary Component"):
        logger.warning("Salary Component table does not exist")
        return False

    try:
        frappe.db.begin()
        components = config.get("salary_components", {})
        if not components:
            logger.warning("No salary components found in configuration")
            raise ValidationError("No salary components found in configuration")

        company = frappe.db.get_default("company")
        if not company and frappe.db.table_exists("Company"):
            companies = frappe.get_all("Company", pluck="name")
            company = companies[0] if companies else None

        success_count = 0
        total_count = 0
        tax_effect_types = get_tax_effect_types()

        for component_type in ["earnings", "deductions"]:
            if component_type not in components:
                continue

            for comp_data in components[component_type]:
                total_count += 1
                component_name = comp_data.get("name")

                if not component_name:
                    logger.warning("Component name is missing in config")
                    continue

                if frappe.db.exists("Salary Component", component_name):
                    component = frappe.get_doc("Salary Component", component_name)
                    is_new = False
                else:
                    component = frappe.new_doc("Salary Component")
                    component.salary_component = component_name
                    is_new = True

                component.salary_component_abbr = comp_data.get("abbr", component_name[:3].upper())
                component.type = "Earning" if component_type == "earnings" else "Deduction"

                # Set optional fields if provided
                for field in [
                    "is_tax_applicable",
                    "variable_based_on_taxable_salary",
                    "statistical_component",
                    "do_not_include_in_total",
                    "exempted",
                ]:
                    if field in comp_data:
                        setattr(component, field, comp_data.get(field))

                if component_name == "PPh 21":
                    component.description = "PPh 21 (PMK 168/2023)"

                component.round_to_the_nearest_integer = 1

                # Determine GL account for mapping
                account_name = None
                if company:
                    account_name = get_gl_account_for_salary_component(company, component_name)

                # Set tax effect type if mapping provided
                if "tax_effect_by_type" in comp_data:
                    mapping = next(
                        (
                            m
                            for m in comp_data.get("tax_effect_by_type", [])
                            if m.get("component_type") == component.type
                        ),
                        None,
                    )
                    if mapping:
                        component.tax_effect_type = mapping.get("tax_effect_type")

                component.flags.ignore_permissions = True

                if is_new:
                    component.insert(ignore_permissions=True)
                    logger.info(f"Created salary component: {component_name}")
                else:
                    component.save(ignore_permissions=True)
                    logger.info(f"Updated salary component: {component_name}")

                if company and account_name:
                    _map_component_to_account(component_name, company, account_name)

                success_count += 1

        logger.info(
            f"Processed {success_count} of {total_count} salary components successfully"
        )
        frappe.db.commit()
        logger.info("Salary components transaction committed successfully")
        return success_count > 0

    except Exception as e:
        frappe.db.rollback()
        logger.error(f"Error setting up salary components, rolling back: {str(e)}")
        raise


def setup_default_salary_structure():
    """
    Create default salary structure using the helper from salary_structure module.

    Returns:
        bool: True if created or already exists, False otherwise
    """
    try:
        # First check if a default structure already exists using the standard names
        default_names = [
            "Default Salary Structure",
            "Default Structure",
            "Indonesia Standard Structure",
            "Payroll Indonesia Default",
        ]

        existing_structure = None
        for name in default_names:
            if frappe.db.exists("Salary Structure", name):
                logger.info(f"Default salary structure already exists: {name}")
                existing_structure = name
                break

        result = False

        # If no structure exists, try to create the standard one first
        if not existing_structure:
            logger.info("Creating default salary structure with standard method")
            result = salary_structure.ensure_default_salary_structure()

        if result:
            logger.info("Default salary structure created successfully")
            return True
        else:
            logger.warning("Standard method failed, trying alternative method")

        # If the standard method failed or we didn't try it, use the alternative method
        # which always attempts to create a structure with a different name
        if not result:
            logger.info("Creating default salary structure with alternative method")
            result = salary_structure.create_default_salary_structure()
            if result:
                logger.info("Default salary structure created successfully with alternative method")
                return True
            else:
                logger.warning("Alternative method also failed to create salary structure")
                return False

    except Exception as e:
        logger.error(f"Error setting up default salary structure: {str(e)}")
        raise


def setup_company_accounts(doc=None, method=None, company=None, config=None):
    """Create payroll GL accounts for a specific company.

    This can be triggered from the ``Company`` DocType hooks or called directly
    with a company name.  When executed from hooks ``doc`` will be the Company
    document instance.

    Args:
        doc: Optional ``Company`` document when called by Frappe hooks.
        method: Unused hook parameter.
        company: Company name when invoked programmatically.
        config: Optional configuration dictionary. ``defaults.json`` will be
            loaded when not provided.

    Returns:
        bool: ``True`` on success, ``False`` otherwise.
    """

    try:
        company_name = company or getattr(doc, "name", None)
        if not company_name:
            logger.warning("setup_company_accounts called without company name")
            return False

        if config is None:
            config = get_default_config()

        setup_accounts(config=config, specific_company=company_name)

        # Create expense accounts for standard salary components
        gl_accounts = config.get("gl_accounts", {}).get("expense_accounts", {})
        for key in ["beban_gaji_pokok", "beban_tunjangan_makan", "beban_tunjangan_transport"]:
            if key in gl_accounts:
                map_gl_account(company_name, key, "expense_accounts")

        logger.info(f"[PAYROLL] GL accounts created for: {company_name}")
        return True
    except Exception as e:
        logger.error(f"[PAYROLL] setup_company_accounts failed for {company_name}: {str(e)}")
        frappe.log_error(
            f"setup_company_accounts failed for {company_name}: {str(e)}",
            "Payroll Indonesia Setup",
        )
        return False


def display_installation_summary(results, config):
    """
    Display installation summary.

    Args:
        results: Dictionary of setup results
        config: Configuration dictionary from defaults.json
    """
    summary = (
        "=== PAYROLL INDONESIA INSTALLATION SUMMARY ===\n"
        f"Accounts setup: {'Success' if results.get('accounts') else 'Failed'}\n"
        f"Suppliers setup: {'Success' if results.get('suppliers') else 'Failed'}\n"
        f"Settings setup: {'Success' if results.get('settings') else 'Failed'}\n"
        f"Salary components: {'Success' if results.get('salary_components') else 'Failed'}\n"
        f"Salary structure: {'Success' if results.get('salary_structure') else 'Skipped'}\n"
        "===================================\n"
        "PMK 168/2023 Implementation: DONE\n"
        "==================================="
    )

    logger.info(summary)
    print(summary)
