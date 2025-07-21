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
from payroll_indonesia.setup.bpjs import ensure_bpjs_account_mappings
from payroll_indonesia.payroll_indonesia.utils import get_or_create_account, find_parent_account
from payroll_indonesia.utilities.install_flag import (
    is_installation_complete,
    mark_installation_complete,
)

from frappe.installer import update_site_config


# Define exported functions
__all__ = [
    "before_install",
    "after_install",
    "after_sync",
    "perform_essential_setup",
    "check_system_readiness",
    "setup_chart_of_accounts",
    "create_non_bpjs_expense_accounts",
    "create_supplier_group",
    "create_bpjs_supplier",
    "setup_salary_components",
    "map_salary_component_to_gl",
    "setup_default_salary_structure",
    "display_installation_summary",
    "setup_pph21_ter",
    "setup_income_tax_slab",
    "setup_company",
    "load_gl_defaults",
    "create_bpjs_accounts",
]


AFTER_SYNC_FLAG_KEY = "payroll_indonesia_after_sync_completed"


def is_after_sync_completed() -> bool:
    """Check site config to see if after_sync has completed."""
    try:
        conf = frappe.get_site_config()
        return bool(conf.get(AFTER_SYNC_FLAG_KEY))
    except Exception:
        return False


def mark_after_sync_completed() -> None:
    """Record in site config that after_sync has completed."""
    try:
        update_site_config(AFTER_SYNC_FLAG_KEY, 1)
    except Exception:
        pass


def _run_full_install(config=None, skip_existing=False):
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

        # Create and populate Payroll Indonesia Settings
        results["settings"] = setup_payroll_settings(transaction_open=True)
        logger.info("Payroll Indonesia Settings setup completed")

        # Setup salary components
        results["salary_components"] = setup_salary_components(
            config, transaction_open=True, skip_existing=skip_existing
        )
        logger.info("Salary components setup completed")

        # Setup accounts
        results["accounts"] = setup_chart_of_accounts(config, skip_existing=skip_existing)
        ensure_bpjs_account_mappings(transaction_open=True)
        logger.info("Account setup completed")

        # Map salary components to GL accounts now that accounts exist
        try:
            if (
                frappe.db.table_exists("Company")
                and frappe.db.table_exists("Salary Component")
                and frappe.db.table_exists("Account")
            ):
                companies = frappe.get_all("Company", pluck="name")
                for comp in companies:
                    map_salary_component_to_gl(comp, config)
        except Exception as e:
            logger.warning(f"Error mapping salary components to GL: {str(e)}")

        # Setup suppliers
        suppliers_ok = create_supplier_group(skip_existing=skip_existing)
        if suppliers_ok and config.get("suppliers", {}).get("bpjs", {}):
            suppliers_ok = create_bpjs_supplier(config, skip_existing=skip_existing)
        results["suppliers"] = suppliers_ok
        logger.info("Supplier setup completed")

        # Setup default salary structure
        results["salary_structure"] = setup_default_salary_structure(skip_existing=skip_existing)
        logger.info("Default salary structure setup completed")

        # Setup TER rates if needed and tax calculation method is TER
        try:
            settings_doc = frappe.get_single("Payroll Indonesia Settings")
            if settings_doc.tax_calculation_method == "TER" and not frappe.db.exists(
                "PPh 21 TER Table", {"status_pajak": ["in", ["TER A", "TER B", "TER C"]]}
            ):
                setup_pph21_ter(config, transaction_open=True)
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


def perform_essential_setup(config=None):
    """Run minimal setup tasks required post-migration."""
    return _run_full_install(config=config, skip_existing=True)


def after_install():
    """
    Main after_install hook for the Payroll Indonesia app.
    Runs all setup steps in sequence and logs results.

    This is automatically called by Frappe after app installation.
    """
    logger.info("Starting Payroll Indonesia after_install process")

    if getattr(frappe.flags, "_payroll_initialized", False):
        return

    if is_installation_complete():
        logger.info("Installation flag detected, skipping full install")
        return

    # Ensure required tables exist before running setup
    if not frappe.db.table_exists("Salary Component"):
        logger.warning("Skipping after_install: Salary Component table missing")
        return
    if not frappe.db.table_exists("Account"):
        logger.warning("Skipping after_install: Account table missing")
        return

    try:
        _run_full_install(skip_existing=True)
        frappe.flags._payroll_initialized = True
        mark_installation_complete()
    except Exception as e:
        logger.error(f"Error during installation: {str(e)}", exc_info=True)
        frappe.log_error(
            f"Error during installation: {str(e)}\n\n{frappe.get_traceback()}",
            "Installation Error",
        )


def after_sync():
    """Run installation routines after Frappe sync."""
    logger.info("Starting after_sync process for Payroll Indonesia")

    if getattr(frappe.flags, "_payroll_initialized", False):
        return

    if is_after_sync_completed():
        logger.info("after_sync already completed, skipping")
        return

    if is_installation_complete():
        logger.info("Installation flag detected, skipping full install")
        mark_after_sync_completed()
        return

    # Ensure required tables exist before running setup
    if not frappe.db.table_exists("Salary Component"):
        logger.warning("Skipping after_sync: Salary Component table missing")
        return
    if not frappe.db.table_exists("Account"):
        logger.warning("Skipping after_sync: Account table missing")
        return

    try:
        # Run full installation but skip existing records so it's idempotent
        _run_full_install(skip_existing=True)

        frappe.flags._payroll_initialized = True
        logger.info("after_sync process completed successfully")

        mark_installation_complete()
        mark_after_sync_completed()

    except Exception as e:
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


def setup_payroll_settings(transaction_open=False):
    """
    Setup Payroll Indonesia Settings with default values.

    Returns:
        bool: True if successful, False otherwise
    """
    if not frappe.db.table_exists("Payroll Indonesia Settings"):
        logger.warning("Payroll Indonesia Settings table does not exist")
        return False

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
        results = migrate_all_settings(transaction_open=transaction_open)

        logger.info("Payroll Indonesia Settings configured successfully")
        return True

    except Exception as e:
        logger.error(f"Error setting up Payroll Indonesia Settings: {str(e)}")
        raise


def setup_chart_of_accounts(config=None, specific_company=None, *, skip_existing=False):
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
        if skip_existing and frappe.db.exists(
            "Account",
            {
                "company": company.name,
                "account_name": "PPh 21 Payable",
            },
        ):
            logger.info(f"Accounts for {company.name} already exist, skipping")
            results["skipped"].append(company.name)
            continue

        try:
            # Create parent accounts
            liability_parent = create_parent_liability_account(company.name)
            expense_parent = create_parent_expense_account(company.name)

            # Create tax payable account
            get_or_create_account(
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


def create_non_bpjs_expense_accounts(company: str, config: dict) -> list[str]:
    """Create non-BPJS expense accounts from ``defaults.json``.

    Accounts are created under the **Direct Expenses** group when it exists,
    otherwise the function falls back to the company's root **Expenses** account.

    Args:
        company: Company name for which accounts will be created.
        config: Loaded configuration dictionary.

    Returns:
        list[str]: Names of accounts created.
    """

    if not frappe.db.table_exists("Account"):
        logger.warning("Account table does not exist")
        return []

    expense_defs = config.get("gl_accounts", {}).get("expense_accounts", {})
    if not expense_defs:
        logger.debug("No expense_accounts definitions found in config")
        return []

    parent = frappe.db.get_value(
        "Account",
        {
            "account_name": "Direct Expenses",
            "company": company,
            "is_group": 1,
        },
        "name",
    )
    if not parent:
        abbr = frappe.get_cached_value("Company", company, "abbr")
        root_name = f"Expenses - {abbr}" if abbr else None
        parent = root_name if root_name and frappe.db.exists("Account", root_name) else None
        if not parent:
            parent = find_parent_account(company, "Expense Account", "Expense")

    created = []
    for key, acc in expense_defs.items():
        if "bpjs" in key.lower():
            continue
        acc_name = acc.get("account_name")
        if not acc_name:
            continue
        if frappe.db.exists("Account", {"account_name": acc_name, "company": company}):
            continue

        account_type = acc.get("account_type", "Direct Expense")
        root_type = acc.get("root_type", "Expense")
        is_group = cint(acc.get("is_group", 0))

        new_acc = get_or_create_account(
            company=company,
            account_name=acc_name,
            account_type=account_type,
            is_group=is_group,
            root_type=root_type,
            parent_account=parent,
        )

        if new_acc:
            created.append(new_acc)

    logger.debug(f"Created non-BPJS expense accounts for {company}: {created}")
    return created


def map_salary_component_to_gl(company: str, gl_defaults: dict) -> list[str]:
    """Map default salary components to their GL expense accounts.

    The mapping supports Indonesian and English component names and is safe to
    run multiple times.

    Args:
        company: Company name for which to map accounts.
        gl_defaults: ``defaults.json`` configuration dictionary.

    Returns:
        list[str]: Salary component names that were mapped.
    """

    if not frappe.db.table_exists("Salary Component") or not frappe.db.table_exists("Account"):
        logger.warning("Required tables for salary component mapping do not exist")
        return []

    expense_defs = gl_defaults.get("gl_accounts", {}).get("expense_accounts", {})
    if not expense_defs:
        logger.debug("No expense account definitions found in defaults")
        return []

    component_map = {
        ("Gaji Pokok", "Basic Salary"): "beban_gaji_pokok",
        ("Bonus",): "beban_bonus",
        ("Tunjangan Makan", "Meal Allowance"): "beban_tunjangan_makan",
        ("Insentif", "Incentive"): "beban_insentif",
    }

    mapped: list[str] = []
    for names, key in component_map.items():
        if key not in expense_defs:
            continue

        for name in names:
            component = frappe.db.get_value("Salary Component", {"salary_component": name}, "name")
            if not component:
                continue

            account_name = map_gl_account(company, key, "expense_accounts")
            if account_name:
                _map_component_to_account(component, company, account_name)
                mapped.append(component)
            break

    logger.debug(f"Mapped salary components to GL for {company}: {mapped}")
    return mapped


def create_supplier_group(*, skip_existing=False):
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
            if skip_existing:
                logger.info("Government supplier group already exists, skipping")
                return True
            group = frappe.get_doc("Supplier Group", "Government")
        else:
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


def create_bpjs_supplier(config, *, skip_existing=False):
    """
    Create BPJS supplier entity from config.

    Args:
        config: Configuration dictionary from defaults.json
        skip_existing: If True, skip creation if supplier already exists

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
            if skip_existing:
                logger.info(f"Supplier {supplier_name} already exists, skipping")
                return True
            supplier = frappe.get_doc("Supplier", supplier_name)
            is_new = False
        else:
            supplier = frappe.new_doc("Supplier")
            supplier.supplier_name = supplier_name
            is_new = True

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

        supplier.supplier_group = supplier_group
        supplier.supplier_type = supplier_config.get("supplier_type", "Government")
        supplier.country = supplier_config.get("country", "Indonesia")
        supplier.default_currency = supplier_config.get("default_currency", "IDR")
        supplier.flags.ignore_permissions = True
        if is_new:
            supplier.insert(ignore_permissions=True)
            logger.info(f"Created supplier: {supplier_name}")
        else:
            supplier.save(ignore_permissions=True)
            logger.info(f"Updated supplier: {supplier_name}")

        return True

    except Exception as e:
        logger.error(f"Failed to create BPJS supplier: {str(e)}")
        raise


def setup_pph21_ter(defaults=None, transaction_open=False):
    """
    Setup PPh 21 TER rates and other required tables in Payroll Indonesia Settings.

    Args:
        defaults: Configuration data, loaded from defaults.json if None

    Returns:
        bool: True if setup was successful, False otherwise
    """
    if not frappe.db.table_exists("Payroll Indonesia Settings"):
        logger.warning("Payroll Indonesia Settings table does not exist")
        return False

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
        if not transaction_open:
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


def setup_salary_components(config, transaction_open=False, *, skip_existing=False):
    """
    Create or update salary components using config data.

    Args:
        config: Configuration dictionary from defaults.json
        transaction_open: Whether transaction is already open
        skip_existing: If True, skip components that already exist

    Returns:
        bool: True if successful, False otherwise
    """
    if not frappe.db.table_exists("Salary Component"):
        logger.warning("Salary Component table does not exist")
        return False

    try:
        if not transaction_open:
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
                    if skip_existing:
                        logger.info(f"Salary component {component_name} already exists, skipping")
                        continue
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

                success_count += 1

        logger.info(f"Processed {success_count} of {total_count} salary components successfully")
        if not transaction_open:
            frappe.db.commit()
        logger.info("Salary components transaction committed successfully")
        return success_count > 0

    except Exception as e:
        if not transaction_open:
            frappe.db.rollback()
        logger.error(f"Error setting up salary components, rolling back: {str(e)}")
        raise


def setup_default_salary_structure(*, skip_existing=False):
    """
    Create default salary structure using the helper from salary_structure module.

    Args:
        skip_existing: If True, skip creation if a default structure already exists

    Returns:
        bool: True if created or already exists, False otherwise
    """
    if not frappe.db.table_exists("Salary Structure"):
        logger.warning("Salary Structure table does not exist")
        return False

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
                if skip_existing:
                    logger.info(f"Default salary structure already exists: {name}, skipping")
                    return True
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


def setup_company_accounts(
    doc=None, method=None, company=None, config=None, *, skip_existing=False
):
    """Create payroll GL accounts for a specific company.

    This can be triggered from the ``Company`` DocType hooks or called directly
    with a company name. When executed from hooks ``doc`` will be the Company
    document instance.

    Args:
        doc: Optional ``Company`` document when called by Frappe hooks.
        method: Unused hook parameter.
        company: Company name when invoked programmatically.
        config: Optional configuration dictionary. ``defaults.json`` will be
            loaded when not provided.
        skip_existing: If True, skip accounts that already exist

    Returns:
        bool: ``True`` on success, ``False`` otherwise.
    """

    if not frappe.db.table_exists("Account"):
        logger.warning("Account table does not exist")
        return False

    try:
        company_name = company or getattr(doc, "name", None)
        if not company_name:
            logger.warning("setup_company_accounts called without company name")
            return False

        if config is None:
            config = get_default_config()

        setup_chart_of_accounts(
            config=config, specific_company=company_name, skip_existing=skip_existing
        )

        # Create non-BPJS expense accounts defined in defaults.json
        create_non_bpjs_expense_accounts(company_name, config)

        # Create expense accounts for standard salary components
        gl_accounts = config.get("gl_accounts", {}).get("expense_accounts", {})
        for key in [
            "beban_gaji_pokok",
            "beban_tunjangan_makan",
            "beban_tunjangan_transport",
            "beban_insentif",
            "beban_bonus",
            "beban_tunjangan_jabatan",
            "beban_tunjangan_lembur",
            "beban_natura",
            "beban_fasilitas_kendaraan",
        ]:
            if key in gl_accounts:
                map_gl_account(company_name, key, "expense_accounts")

        # Map salary components to their GL accounts for this company
        salary_components_cfg = config.get("salary_components", {})
        component_names = [c.get("name") for c in salary_components_cfg.get("earnings", [])]
        component_names += [c.get("name") for c in salary_components_cfg.get("deductions", [])]

        for component_name in filter(None, component_names):
            account_name = get_gl_account_for_salary_component(company_name, component_name)
            if account_name:
                _map_component_to_account(component_name, company_name, account_name)

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


def load_gl_defaults() -> dict:
    """Load GL account defaults from ``defaults.json``."""
    defaults = _load_defaults()
    return defaults.get("gl_accounts", {}) if defaults else {}


def create_bpjs_accounts(company: str, gl_defaults: dict) -> list[str]:
    """Create BPJS payable and expense accounts for ``company``."""
    if not frappe.db.table_exists("Account"):
        logger.warning("Account table does not exist")
        return []

    from payroll_indonesia.payroll_indonesia.utils import (
        get_or_create_account,
        create_parent_liability_account,
        create_parent_expense_account,
    )

    create_parent_liability_account(company)
    create_parent_expense_account(company)

    created: list[str] = []

    for defs, is_expense in [
        (gl_defaults.get("bpjs_expense_accounts", {}), True),
        (gl_defaults.get("bpjs_payable_accounts", {}), False),
    ]:
        for info in defs.values():
            name = info.get("account_name")
            if not name:
                continue
            if frappe.db.exists("Account", {"account_name": name, "company": company}):
                continue

            account_type = info.get(
                "account_type", "Expense Account" if is_expense else "Payable"
            )
            root_type = info.get("root_type", "Expense" if is_expense else "Liability")

            acc = get_or_create_account(
                company=company,
                account_name=name,
                account_type=account_type,
                is_group=0,
                root_type=root_type,
            )
            if acc:
                created.append(acc)

    logger.debug(f"Created BPJS accounts for {company}: {created}")
    return created


def setup_company(company: str) -> bool:
    """Run essential setup steps for a new company."""

    required = ["Account", "Salary Component", "Supplier", "Salary Structure"]
    if not all(frappe.db.table_exists(dt) for dt in required):
        logger.warning("Skipping setup_company: required tables missing")
        return False

    defaults = _load_defaults()
    if not defaults:
        logger.warning("Could not load defaults.json for company setup")
        return False

    gl_defaults = defaults.get("gl_accounts", {})

    create_bpjs_accounts(company, gl_defaults)
    create_non_bpjs_expense_accounts(company, defaults)
    create_bpjs_supplier(defaults)
    ensure_bpjs_account_mappings(doc=frappe.get_doc("Company", company))

    # Make sure we pass defaults to the mapping function
    map_salary_component_to_gl(company, defaults)

    setup_default_salary_structure(skip_existing=True)

    logger.info(f"Completed setup for company {company}")
    return True
