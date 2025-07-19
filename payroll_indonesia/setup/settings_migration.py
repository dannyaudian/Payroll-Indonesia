# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-03 04:42:49 by dannyaudian

"""
Settings Migration Module

Provides utility functions for migrating configuration settings from defaults.json
to Payroll Indonesia Settings document and its child tables.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import frappe
from frappe import _
from frappe.utils import flt, cint, now_datetime

from payroll_indonesia.frappe_helpers import logger


def migrate_cli():
    """
    Command-line entry point for migrating settings.
    Can be run with: bench --site <site> execute payroll_indonesia.setup.settings_migration.migrate_cli
    """
    try:
        logger.info("Starting migration of settings from defaults.json")

        results = migrate_all_settings()

        # Check if any changes were made
        changes_made = any(results.values())

        if changes_made:
            logger.info("Successfully migrated settings from defaults.json")
            print("Settings migration completed successfully")

            # Log summary
            success_count = sum(1 for result in results.values() if result)
            total_count = len(results)
            print(f"Migration summary: {success_count}/{total_count} sections updated")
        else:
            logger.info("No changes needed, all settings already populated")
            print("No changes needed, all settings already populated")

    except Exception as e:
        logger.error(f"Error during settings migration: {str(e)}")
        print(f"Error during settings migration: {str(e)}")


def migrate_all_settings(settings_doc=None, defaults=None, *args, **kwargs) -> Dict[str, bool]:
    """
    Migrate all settings from defaults.json to Payroll Indonesia Settings.

    Args:
        settings_doc: Payroll Indonesia Settings document (loads if None)
        defaults: Configuration data from defaults.json (loads if None)

    Returns:
        Dict[str, bool]: Status of each migration section
    """
    frappe.db.begin()
    try:
        # Load settings document if not provided
        if settings_doc is None:
            try:
                settings_doc = frappe.get_single("Payroll Indonesia Settings")
                settings_doc.flags.ignore_validate = True
                settings_doc.flags.ignore_permissions = True
            except Exception as e:
                logger.error(f"Error fetching Payroll Indonesia Settings: {str(e)}")
                raise

        # Load defaults if not provided
        if defaults is None:
            defaults = _load_defaults()
            if not defaults:
                logger.error("Could not load defaults.json")
                raise Exception("Failed to load defaults.json")

        results = {}

        # Migrate TER rates
        if hasattr(settings_doc, "ter_rate_table"):
            results["ter_rates"] = _seed_ter_rates(settings_doc, defaults)

        # Migrate PTKP values
        if hasattr(settings_doc, "ptkp_table"):
            results["ptkp_values"] = _seed_ptkp_values(settings_doc, defaults)

        # Migrate PTKP to TER mapping
        if hasattr(settings_doc, "ptkp_ter_mapping_table"):
            results["ptkp_ter_mapping"] = _seed_ptkp_ter_mapping(settings_doc, defaults)

        # Migrate tax brackets
        if hasattr(settings_doc, "tax_brackets_table"):
            results["tax_brackets"] = _seed_tax_brackets(settings_doc, defaults)

        # Migrate employee types
        if hasattr(settings_doc, "tipe_karyawan"):
            results["employee_types"] = _seed_tipe_karyawan(settings_doc, defaults)

        # Update general settings
        results["general_settings"] = _update_general_settings(settings_doc, defaults)

        # Update BPJS settings
        bpjs_result = _update_bpjs_settings(settings_doc, defaults)
        results["bpjs_settings"] = bpjs_result
        results["account_mappings"] = bpjs_result  # Alias as requested

        # Seed GL account mappings
        results["gl_account_mappings"] = _seed_gl_account_mappings(settings_doc, defaults)

        # Save if we created the settings doc
        if not getattr(settings_doc, "_doc_before_save", None):
            settings_doc.save()

        frappe.db.commit()

        # Log summary
        success_count = sum(1 for result in results.values() if result)
        total_count = len(results)

        logger.info(
            f"Settings migration summary: {success_count}/{total_count} sections updated"
        )
        for section, success in results.items():
            status = "updated" if success else "skipped"
            logger.info(f"Section '{section}': {status}")

        return results
    except Exception as e:
        frappe.db.rollback()
        logger.error(f"Error during settings migration: {str(e)}")
        raise


def _load_defaults() -> Dict[str, Any]:
    """
    Load defaults from defaults.json.

    Returns:
        Dict: Configuration from defaults.json
    """
    try:
        # Get app path
        app_path = frappe.get_app_path("payroll_indonesia")
        config_path = Path(app_path) / "config"
        defaults_file = config_path / "defaults.json"

        if not defaults_file.exists():
            logger.warning(f"defaults.json not found at {defaults_file}")
            return {}

        with open(defaults_file, "r") as f:
            defaults = json.load(f)

        logger.info(f"Loaded defaults.json with {len(defaults)} sections")
        return defaults

    except Exception as e:
        logger.error(f"Error loading defaults.json: {str(e)}")
        return {}


def _seed_ter_rates(settings: "frappe.Document", defaults: Dict[str, Any]) -> bool:
    """
    Seed TER rates from defaults.json.

    Args:
        settings: Payroll Indonesia Settings document
        defaults: Configuration from defaults.json

    Returns:
        bool: True if rates were added, False otherwise
    """
    try:
        # Skip if table already has data
        if settings.ter_rate_table:
            logger.info("TER rates table already has data, skipping")
            return False

        # Get TER rates from defaults
        ter_rates = defaults.get("ter_rates", {})
        if not ter_rates:
            logger.warning("No TER rates found in defaults.json")
            return False

        # Set metadata if available
        metadata = ter_rates.get("metadata", {})
        if metadata:
            if hasattr(settings, "ter_effective_date") and metadata.get("effective_date"):
                settings.ter_effective_date = metadata.get("effective_date")

            if hasattr(settings, "ter_regulation_ref") and metadata.get("regulation_ref"):
                settings.ter_regulation_ref = metadata.get("regulation_ref")

            if hasattr(settings, "ter_description") and metadata.get("description"):
                settings.ter_description = metadata.get("description")

            if hasattr(settings, "ter_default_category") and metadata.get("default_category"):
                settings.ter_default_category = metadata.get("default_category")

            if hasattr(settings, "ter_fallback_rate") and metadata.get("fallback_rate"):
                settings.ter_fallback_rate = flt(metadata.get("fallback_rate"))

        # Prepare TER rate table rows
        ter_rate_table_rows = []

        # Convert dict structure to list of rows
        for category, rates in ter_rates.items():
            # Skip metadata
            if category == "metadata":
                continue

            # Process each rate in this category
            for rate_data in rates:
                # Create a new row with all needed fields
                new_row = {
                        "status_pajak": category,
                    "ter_category": category,  # Additional field for clarity
                    "income_from": flt(rate_data.get("income_from", 0)),
                    "income_to": flt(rate_data.get("income_to", 0)),
                    "rate": flt(rate_data.get("rate", 0)),
                    "is_highest_bracket": cint(rate_data.get("is_highest_bracket", 0)),
                    "description": f"TER rate for {category}: {flt(rate_data.get('income_from', 0)):,.0f} to {flt(rate_data.get('income_to', 0)):,.0f}"
                }
                ter_rate_table_rows.append(new_row)

        # Set the table in settings
        settings.set("ter_rate_table", [])
        for row in ter_rate_table_rows:
            settings.append("ter_rate_table", row)

        logger.info(f"Added {len(ter_rate_table_rows)} TER rates")
        return len(ter_rate_table_rows) > 0
    except Exception as e:
        logger.error(f"Error seeding TER rates: {str(e)}")
        raise


def _seed_ptkp_values(settings: "frappe.Document", defaults: Dict[str, Any]) -> bool:
    """
    Seed PTKP values from defaults.json.

    Args:
        settings: Payroll Indonesia Settings document
        defaults: Configuration from defaults.json

    Returns:
        bool: True if values were added, False otherwise
    """
    try:
        # Skip if table already has data
        if settings.ptkp_table:
            logger.info("PTKP table already has data, skipping")
            return False

        # Get PTKP values from defaults
        ptkp_values = defaults.get("ptkp", {})
        if not ptkp_values:
            logger.warning("No PTKP values found in defaults.json")
            return False

        # Add PTKP values
        count = 0
        for status, amount in ptkp_values.items():
            settings.append("ptkp_table", {"status_pajak": status, "ptkp_amount": flt(amount)})
            count += 1

        logger.info(f"Added {count} PTKP values")
        return count > 0

    except Exception as e:
        logger.error(f"Error seeding PTKP values: {str(e)}")
        raise


def _seed_ptkp_ter_mapping(settings: "frappe.Document", defaults: Dict[str, Any]) -> bool:
    """
    Seed PTKP to TER mapping from defaults.json.

    Args:
        settings: Payroll Indonesia Settings document
        defaults: Configuration from defaults.json

    Returns:
        bool: True if mappings were added, False otherwise
    """
    try:
        # Skip if table already has data
        if settings.ptkp_ter_mapping_table:
            logger.info("PTKP-TER mapping table already has data, skipping")
            return False

        # Get mapping from defaults
        mapping = defaults.get("ptkp_to_ter_mapping", {})
        if not mapping:
            logger.warning("No PTKP to TER mapping found in defaults.json")
            return False

        # Add mappings
        count = 0
        for ptkp_status, ter_category in mapping.items():
            settings.append(
                "ptkp_ter_mapping_table", {"ptkp_status": ptkp_status, "ter_category": ter_category}
            )
            count += 1

        logger.info(f"Added {count} PTKP-TER mappings")
        return count > 0

    except Exception as e:
        logger.error(f"Error seeding PTKP-TER mapping: {str(e)}")
        raise


def _seed_tax_brackets(settings: "frappe.Document", defaults: Dict[str, Any]) -> bool:
    """
    Seed tax brackets from defaults.json.

    Args:
        settings: Payroll Indonesia Settings document
        defaults: Configuration from defaults.json

    Returns:
        bool: True if brackets were added, False otherwise
    """
    try:
        # Skip if table already has data
        if settings.tax_brackets_table:
            logger.info("Tax brackets table already has data, skipping")
            return False

        # Get tax brackets from defaults
        brackets = defaults.get("tax_brackets", [])
        if not brackets:
            logger.warning("No tax brackets found in defaults.json")
            return False

        # Add tax brackets
        count = 0
        for bracket in brackets:
            settings.append(
                "tax_brackets_table",
                {
                    "income_from": flt(bracket.get("income_from", 0)),
                    "income_to": flt(bracket.get("income_to", 0)),
                    "tax_rate": flt(bracket.get("tax_rate", 0)),
                },
            )
            count += 1

        logger.info(f"Added {count} tax brackets")
        return count > 0

    except Exception as e:
        logger.error(f"Error seeding tax brackets: {str(e)}")
        raise


def _seed_tipe_karyawan(settings: "frappe.Document", defaults: Dict[str, Any]) -> bool:
    """
    Seed employee types from defaults.json.

    Args:
        settings: Payroll Indonesia Settings document
        defaults: Configuration from defaults.json

    Returns:
        bool: True if types were added, False otherwise
    """
    try:
        # Skip if table already has data
        if settings.tipe_karyawan:
            logger.info("Employee types table already has data, skipping")
            return False

        # Get employee types from defaults
        tipe_karyawan = defaults.get("tipe_karyawan", [])
        if not tipe_karyawan:
            # Use hardcoded defaults if none in config
            tipe_karyawan = ["Tetap", "Tidak Tetap", "Freelance"]

        # Add employee types
        count = 0
        for tipe in tipe_karyawan:
            settings.append("tipe_karyawan", {"tipe_karyawan": tipe})
            count += 1

        logger.info(f"Added {count} employee types")
        return count > 0

    except Exception as e:
        logger.error(f"Error seeding employee types: {str(e)}")
        raise


def _update_general_settings(settings: "frappe.Document", defaults: Dict[str, Any]) -> bool:
    """
    Update general settings from defaults.json.

    Args:
        settings: Payroll Indonesia Settings document
        defaults: Configuration from defaults.json

    Returns:
        bool: True if settings were updated, False otherwise
    """
    try:
        changes_made = False

        # Tax settings
        tax_config = defaults.get("tax", {})
        if tax_config:
            tax_fields = [
                ("biaya_jabatan_percent", "biaya_jabatan_percent", 5.0),
                ("biaya_jabatan_max", "biaya_jabatan_max", 500000.0),
                ("npwp_mandatory", "npwp_mandatory", 0),
                ("tax_calculation_method", "tax_calculation_method", "TER"),
                ("use_ter", "use_ter", 1),
                ("use_gross_up", "use_gross_up", 0),
                ("umr_default", "umr_default", 4900000.0),
            ]

            for field, config_key, default_value in tax_fields:
                if hasattr(settings, field) and not getattr(settings, field):
                    value = tax_config.get(config_key, default_value)
                    setattr(settings, field, value)
                    changes_made = True

        # Payroll defaults
        defaults_config = defaults.get("defaults", {})
        if defaults_config:
            default_fields = [
                ("default_currency", "currency", "IDR"),
                ("payroll_frequency", "payroll_frequency", "Monthly"),
                ("salary_slip_based_on", "salary_slip_based_on", "Leave Policy"),
                ("max_working_days_per_month", "max_working_days_per_month", 22),
                ("working_hours_per_day", "working_hours_per_day", 8),
            ]

            for field, config_key, default_value in default_fields:
                if hasattr(settings, field) and not getattr(settings, field):
                    value = defaults_config.get(config_key, default_value)
                    setattr(settings, field, value)
                    changes_made = True

        # Salary structure
        struktur_gaji = defaults.get("struktur_gaji", {})
        if struktur_gaji:
            struktur_fields = [
                ("basic_salary_percent", "basic_salary_percent", 75),
                ("meal_allowance", "meal_allowance", 750000.0),
                ("transport_allowance", "transport_allowance", 900000.0),
                ("struktur_gaji_umr_default", "umr_default", 4900000.0),
                ("position_allowance_percent", "position_allowance_percent", 7.5),
                ("hari_kerja_default", "hari_kerja_default", 22),
            ]

            for field, config_key, default_value in struktur_fields:
                if hasattr(settings, field) and not getattr(settings, field):
                    value = struktur_gaji.get(config_key, default_value)
                    setattr(settings, field, value)
                    changes_made = True

        # Additional key fields as requested
        general_fields = [
            ("sync_to_defaults", defaults.get("sync_to_defaults", 0)),
        ]

        for field, default_value in general_fields:
            if hasattr(settings, field) and not getattr(settings, field):
                # Convert lists/dicts to JSON for Code fields
                if isinstance(default_value, (dict, list)):
                    value = json.dumps(default_value, indent=2)
                else:
                    value = default_value
                setattr(settings, field, value)
                changes_made = True

        return changes_made

    except Exception as e:
        logger.error(f"Error updating general settings: {str(e)}")
        raise


def _update_bpjs_settings(settings: "frappe.Document", defaults: Dict[str, Any]) -> bool:
    """
    Update BPJS settings from defaults.json.

    Args:
        settings: Payroll Indonesia Settings document
        defaults: Configuration from defaults.json

    Returns:
        bool: True if settings were updated, False otherwise
    """
    try:
        changes_made = False

        # BPJS settings
        bpjs_config = defaults.get("bpjs", {})
        if bpjs_config:
            bpjs_fields = [
                ("kesehatan_employee_percent", 1.0),
                ("kesehatan_employer_percent", 4.0),
                ("kesehatan_max_salary", 12000000.0),
                ("jht_employee_percent", 2.0),
                ("jht_employer_percent", 3.7),
                ("jp_employee_percent", 1.0),
                ("jp_employer_percent", 2.0),
                ("jp_max_salary", 9077600.0),
                ("jkk_percent", 0.24),
                ("jkm_percent", 0.3),
            ]

            for field, default_value in bpjs_fields:
                if hasattr(settings, field) and not getattr(settings, field):
                    value = bpjs_config.get(field, default_value)
                    setattr(settings, field, value)
                    changes_made = True

        # JSON/code field mappings
        json_fields = [
            ("bpjs_account_mapping_json", "account_mapping", {}),
            ("expense_accounts_json", "expense_accounts", {}),
            ("payable_accounts_json", "payable_accounts", {}),
            ("parent_accounts_json", "parent_accounts", {}),
        ]

        for field, config_key, default_value in json_fields:
            if hasattr(settings, field) and not getattr(settings, field):
                value = bpjs_config.get(config_key, default_value)
                # Convert dicts/lists to JSON strings for Code fields
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, indent=2)
                setattr(settings, field, value)
                changes_made = True

        return changes_made

    except Exception as e:
        logger.error(f"Error updating BPJS settings: {str(e)}")
        raise


def _seed_gl_account_mappings(settings: "frappe.Document", defaults: Dict[str, Any]) -> bool:
    """
    Populate GL account mapping fields from defaults.json.

    Args:
        settings: Payroll Indonesia Settings document
        defaults: Configuration from defaults.json

    Returns:
        bool: True if settings were updated, False otherwise
    """
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
        ]

        for field, value in candidate_fields:
            if hasattr(settings, field) and not getattr(settings, field) and value is not None:
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, indent=2)
                setattr(settings, field, value)
                changes_made = True

        return changes_made

    except Exception as e:
        logger.error(f"Error updating GL account mappings: {str(e)}")
        raise
