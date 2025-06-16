# -*- coding: utf-8 -*-
# Copyright (c) 2023, PT. Innovasi Terbaik Bangsa and Contributors
# See license.txt

import frappe
import json
import os
from frappe.utils import flt, now, get_datetime
import logging
import hashlib
from payroll_indonesia.config.gl_account_mapper import map_gl_account
from payroll_indonesia.payroll_indonesia.utils import get_default_config, debug_log
from payroll_indonesia.fixtures.setup import setup_accounts

# Global logger setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter("[PI-Install] %(asctime)s - %(levelname)s - %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)


def before_install():
    """Run before app installation"""
    pass


def after_install():
    """
    Run after app installation to set up accounts from defaults.json

    This function:
    1. Loads configuration using get_default_config()
    2. Calls setup_accounts() with the configuration
    3. Logs the success/failure of the setup process
    """
    try:
        # Load configuration from defaults.json
        debug_log("Loading configuration from defaults.json", "GL Account Setup")
        config = get_default_config()

        if not config:
            frappe.logger().error("Failed to load configuration from defaults.json")
            debug_log("Failed to load configuration from defaults.json", "GL Account Setup Error")
            return

        # Check if GL accounts configuration exists
        if not config.get("gl_accounts"):
            frappe.logger().warning("Configuration does not contain gl_accounts section")
            debug_log("Configuration missing gl_accounts section", "GL Account Setup Warning")
            return

        # Set up accounts using the loaded configuration
        frappe.logger().info("Starting GL accounts setup from defaults.json")
        debug_log("Starting GL accounts setup using setup_accounts()", "GL Account Setup")

        # Call setup_accounts with the loaded config
        result = setup_accounts(config)

        # Log the result
        if result:
            frappe.logger().info("GL accounts setup completed successfully")
            debug_log("GL accounts setup completed successfully", "GL Account Setup")
        else:
            frappe.logger().warning("GL accounts setup completed with warnings or errors")
            debug_log(
                "GL accounts setup completed with warnings or errors", "GL Account Setup Warning"
            )

        # Continue with other installation steps
        setup_payroll_components()
        migrate_from_json_to_doctype()

    except Exception as e:
        frappe.logger().error(f"Error during GL accounts setup: {str(e)}\n{frappe.get_traceback()}")
        debug_log(f"Error during GL accounts setup: {str(e)}", "GL Account Setup Error", trace=True)


def after_update():
    """Run after app update"""
    # Apply our salary slip enhancements
    from payroll_indonesia.override.salary_slip import extend_salary_slip_functionality

    extend_salary_slip_functionality()


def after_migrate():
    """Run after app migrations"""
    migrate_from_json_to_doctype()


def setup_payroll_components():
    """Set up required payroll components if missing"""
    components = [
        # Earnings
        {"name": "Gaji Pokok", "type": "Earning", "abbr": "GP", "is_tax_applicable": 1},
        {"name": "Tunjangan Makan", "type": "Earning", "abbr": "TM", "is_tax_applicable": 1},
        {"name": "Tunjangan Transport", "type": "Earning", "abbr": "TT", "is_tax_applicable": 1},
        {"name": "Insentif", "type": "Earning", "abbr": "INS", "is_tax_applicable": 1},
        {"name": "Bonus", "type": "Earning", "abbr": "BON", "is_tax_applicable": 1},
        # Deductions
        {"name": "BPJS Kesehatan Employee", "type": "Deduction", "abbr": "BKE"},
        {"name": "BPJS JHT Employee", "type": "Deduction", "abbr": "BJE"},
        {"name": "BPJS JP Employee", "type": "Deduction", "abbr": "BPE"},
        {
            "name": "PPh 21",
            "type": "Deduction",
            "abbr": "PPH",
            "variable_based_on_taxable_salary": 1,
        },
    ]

    for comp in components:
        if not frappe.db.exists("Salary Component", comp["name"]):
            doc = frappe.new_doc("Salary Component")
            doc.salary_component = comp["name"]
            doc.salary_component_abbr = comp["abbr"]
            doc.type = comp["type"]

            # Add optional fields
            for field in ["is_tax_applicable", "variable_based_on_taxable_salary"]:
                if field in comp:
                    setattr(doc, field, comp[field])

            # Set default company for GL accounts
            company = frappe.defaults.get_global_default("company")
            if company and hasattr(doc, "accounts"):
                # Map the GL account based on component name
                account_name = get_default_gl_account_for_component(company, comp["name"])
                if account_name:
                    doc.append("accounts", {"company": company, "default_account": account_name})

            doc.insert()

    frappe.db.commit()
    logger.info("Payroll Indonesia components setup completed")


def get_default_gl_account_for_component(company, component_name):
    """Get the default GL account for a salary component using map_gl_account"""
    try:
        from payroll_indonesia.config.gl_account_mapper import get_gl_account_for_salary_component

        return get_gl_account_for_salary_component(company, component_name)
    except Exception as e:
        logger.warning(f"Error getting GL account for component {component_name}: {str(e)}")
        return None


def migrate_from_json_to_doctype():
    """
    Migrate settings from defaults.json to the Payroll Indonesia Settings DocType

    This function is idempotent and will:
    - Skip if DocType doesn't exist (with warning)
    - Skip if settings already exist with the same version
    - Create settings if DocType exists but settings don't
    - Update settings if they exist but have a different version

    Returns:
        bool: True if migration was successful, False otherwise
    """
    try:
        # Validasi eksistensi DocType 'Payroll Indonesia Settings'
        if not frappe.db.exists("DocType", "Payroll Indonesia Settings"):
            logger.warning(
                "[PI-Install] Payroll Indonesia Settings DocType not found, skipping migration"
            )
            return False

        # Panggil get_default_config()
        config = get_default_config()
        if not config:
            logger.warning("[PI-Install] Could not load defaults.json, skipping migration")
            return False

        # Log versi & metadata dari config + jumlah key
        app_info = config.get("app_info", {})
        config_version = app_info.get("version", "1.0.0")
        config_updated_by = app_info.get("updated_by", "system")
        config_key_count = len(config.keys())
        logger.info(
            f"[PI-Install] Loaded defaults.json: version={config_version}, updated_by={config_updated_by}, key_count={config_key_count}"
        )

        # Ambil (jika ada) dokumen settings
        try:
            # Try to get the document - will raise DoesNotExistError if not found
            settings = frappe.get_doc("Payroll Indonesia Settings", "Payroll Indonesia Settings")
            settings_exists = True

            # Bandingkan app_version dengan config version
            if settings.app_version == config_version:
                logger.info(
                    f"[PI-Install] Settings already exist with matching version {config_version}, skipping migration"
                )
                return True
            else:
                logger.info(
                    f"[PI-Install] Updating existing settings from version {settings.app_version} to {config_version}"
                )

        except frappe.exceptions.DoesNotExistError:
            # Settings doesn't exist, we'll create a new one
            logger.info("[PI-Install] Creating new Payroll Indonesia Settings")
            settings = frappe.new_doc("Payroll Indonesia Settings")
            settings_exists = False

        # Periksa user login aktif - menggunakan safer approach
        current_user = frappe.session.user
        logger.info(f"[PI-Install] Current user executing migration: {current_user}")

        # Panggil update_settings_from_config()
        update_settings_from_config(settings, config)
        logger.info("[PI-Install] update_settings_from_config() completed")

        # Save / insert sesuai flag settings_exists
        settings.flags.ignore_validate = True
        settings.flags.ignore_permissions = True
        settings.flags.ignore_mandatory = True

        # Set updated_by to current user
        settings.app_updated_by = current_user

        if settings_exists:
            settings.save(ignore_permissions=True)
            logger.info(
                f"[PI-Install] Updated existing Payroll Indonesia Settings (name={settings.name}, version={settings.app_version})"
            )
        else:
            settings.insert(ignore_permissions=True)
            logger.info(
                f"[PI-Install] Created new Payroll Indonesia Settings (name={settings.name}, version={settings.app_version})"
            )

        # Sebelum migrate_ter_rates, konfirmasi eksistensi DocType 'PPh 21 TER Table'
        if frappe.db.exists("DocType", "PPh 21 TER Table"):
            ter_table_count = frappe.db.count("PPh 21 TER Table")
            logger.info(
                f"[PI-Install] PPh 21 TER Table exists with {ter_table_count} entries, proceeding with migration"
            )
        else:
            logger.warning(
                "[PI-Install] PPh 21 TER Table DocType not found, skipping TER rates migration"
            )

        # Panggil migrate_ter_rates()
        migrate_ter_rates_result = migrate_ter_rates(config.get("ter_rates", {}))
        logger.info(f"[PI-Install] migrate_ter_rates() returned {migrate_ter_rates_result}")

        # Panggil sync_to_bpjs_settings()
        sync_to_bpjs_settings(settings)
        logger.info("[PI-Install] sync_to_bpjs_settings() completed")

        # Commit pada sukses
        frappe.db.commit()
        return True

    except Exception as e:
        # Rollback & logger.exception pada failure
        frappe.db.rollback()
        logger.exception(f"[PI-Install] Error in migrate_from_json_to_doctype: {str(e)}")
        return False


def update_settings_from_config(settings, config):
    """
    Update settings document with values from config

    Args:
        settings: Payroll Indonesia Settings document
        config: Configuration data from defaults.json
    """
    try:
        # App info
        app_info = config.get("app_info", {})
        settings.app_version = app_info.get("version", "1.0.0")

        # Fix untuk error get_datetime_str()
        last_updated = app_info.get("last_updated")
        if last_updated:
            settings.app_last_updated = last_updated
        else:
            settings.app_last_updated = now()

        # Use current timestamp for last update
        settings.app_updated_by = frappe.session.user
        app_info_summary = {
            "version": settings.app_version,
            "last_updated": settings.app_last_updated,
            "updated_by": settings.app_updated_by,
        }

        # BPJS settings
        bpjs = config.get("bpjs", {})
        settings.kesehatan_employee_percent = flt(bpjs.get("kesehatan_employee_percent", 1.0))
        settings.kesehatan_employer_percent = flt(bpjs.get("kesehatan_employer_percent", 4.0))
        settings.kesehatan_max_salary = flt(bpjs.get("kesehatan_max_salary", 12000000.0))
        settings.jht_employee_percent = flt(bpjs.get("jht_employee_percent", 2.0))
        settings.jht_employer_percent = flt(bpjs.get("jht_employer_percent", 3.7))
        settings.jp_employee_percent = flt(bpjs.get("jp_employee_percent", 1.0))
        settings.jp_employer_percent = flt(bpjs.get("jp_employer_percent", 2.0))
        settings.jp_max_salary = flt(bpjs.get("jp_max_salary", 9077600.0))
        settings.jkk_percent = flt(bpjs.get("jkk_percent", 0.24))
        settings.jkm_percent = flt(bpjs.get("jkm_percent", 0.3))
        bpjs_summary = {
            "kesehatan_employee_percent": settings.kesehatan_employee_percent,
            "kesehatan_employer_percent": settings.kesehatan_employer_percent,
        }

        # Tax settings
        tax = config.get("tax", {})
        settings.umr_default = flt(tax.get("umr_default", 4900000.0))
        settings.biaya_jabatan_percent = flt(tax.get("biaya_jabatan_percent", 5.0))
        settings.biaya_jabatan_max = flt(tax.get("biaya_jabatan_max", 500000.0))
        settings.npwp_mandatory = tax.get("npwp_mandatory", 0)
        settings.tax_calculation_method = tax.get("tax_calculation_method", "TER")
        settings.use_ter = tax.get("use_ter", 1)
        settings.use_gross_up = tax.get("use_gross_up", 0)
        tax_summary = {
            "umr_default": settings.umr_default,
            "biaya_jabatan_percent": settings.biaya_jabatan_percent,
        }

        # Clear existing tables to prevent duplicates
        settings.ptkp_table = []
        settings.ptkp_ter_mapping_table = []
        settings.tax_brackets_table = []
        settings.tipe_karyawan = []

        # PTKP values
        ptkp = config.get("ptkp", {})
        for status, amount in ptkp.items():
            settings.append("ptkp_table", {"status_pajak": status, "ptkp_amount": flt(amount)})
        ptkp_summary = {"count": len(settings.ptkp_table)}

        # PTKP to TER mapping
        ptkp_ter_mapping = config.get("ptkp_to_ter_mapping", {})
        for status, category in ptkp_ter_mapping.items():
            settings.append(
                "ptkp_ter_mapping_table", {"ptkp_status": status, "ter_category": category}
            )
        ptkp_ter_mapping_summary = {"count": len(settings.ptkp_ter_mapping_table)}

        # Tax brackets
        tax_brackets = config.get("tax_brackets", [])
        for bracket in tax_brackets:
            settings.append(
                "tax_brackets_table",
                {
                    "income_from": flt(bracket.get("income_from", 0)),
                    "income_to": flt(bracket.get("income_to", 0)),
                    "tax_rate": flt(bracket.get("tax_rate", 0)),
                },
            )
        tax_brackets_summary = {"count": len(settings.tax_brackets_table)}

        # Defaults
        defaults = config.get("defaults", {})
        settings.default_currency = defaults.get("currency", "IDR")
        settings.attendance_based_on_timesheet = defaults.get("attendance_based_on_timesheet", 0)
        settings.payroll_frequency = defaults.get("payroll_frequency", "Monthly")
        settings.salary_slip_based_on = defaults.get("salary_slip_based_on", "Leave Policy")
        settings.max_working_days_per_month = defaults.get("max_working_days_per_month", 22)
        settings.include_holidays_in_total_working_days = defaults.get(
            "include_holidays_in_total_working_days", 0
        )
        settings.working_hours_per_day = flt(defaults.get("working_hours_per_day", 8))
        defaults_summary = {
            "default_currency": settings.default_currency,
            "payroll_frequency": settings.payroll_frequency,
        }

        # Struktur gaji
        struktur_gaji = config.get("struktur_gaji", {})
        settings.basic_salary_percent = flt(struktur_gaji.get("basic_salary_percent", 75))
        settings.meal_allowance = flt(struktur_gaji.get("meal_allowance", 750000.0))
        settings.transport_allowance = flt(struktur_gaji.get("transport_allowance", 900000.0))
        settings.struktur_gaji_umr_default = flt(struktur_gaji.get("umr_default", 4900000.0))
        settings.position_allowance_percent = flt(
            struktur_gaji.get("position_allowance_percent", 7.5)
        )
        settings.hari_kerja_default = struktur_gaji.get("hari_kerja_default", 22)
        struktur_gaji_summary = {
            "basic_salary_percent": settings.basic_salary_percent,
            "meal_allowance": settings.meal_allowance,
        }

        # Tipe karyawan
        tipe_karyawan = config.get("tipe_karyawan", [])
        for tipe in tipe_karyawan:
            settings.append("tipe_karyawan", {"tipe_karyawan": tipe})
        tipe_karyawan_summary = {"count": len(settings.tipe_karyawan)}

        logger.info(
            f"[PI-Install] update_settings_from_config summaries: app_info={app_info_summary}, bpjs={bpjs_summary}, tax={tax_summary}"
        )

    except Exception as e:
        logger.exception(f"[PI-Install] Error in update_settings_from_config: {str(e)}")


def migrate_ter_rates(ter_rates):
    """
    Migrate TER rates from defaults.json to PPh 21 TER Table entries

    Args:
        ter_rates (dict): Dictionary containing TER rates from defaults.json

    Returns:
        bool: True if migration was successful, False otherwise
    """
    try:
        # Validasi eksistensi DocType dan tabel database
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            logger.warning(
                "[PI-Install] PPh 21 TER Table DocType not found, skipping TER rates migration"
            )
            return False

        try:
            existing_entries = frappe.db.count("PPh 21 TER Table")
            logger.info(f"[PI-Install] PPh 21 TER Table exists with {existing_entries} entries")
        except Exception as e:
            logger.warning(f"[PI-Install] PPh 21 TER Table not yet created in database: {str(e)}")
            return False

        # Skip if we already have enough entries
        if existing_entries > 10:  # Arbitrary threshold
            logger.info(
                f"[PI-Install] Found {existing_entries} existing TER entries, skipping TER rates migration"
            )
            return True

        # Check if PPh 21 Settings exists, but do it safely
        pph21_settings_exists = False
        try:
            # Check if the DocType exists first
            if frappe.db.exists("DocType", "PPh 21 Settings"):
                # Then check if the table exists in database by attempting a count
                # This will raise an exception if the table doesn't exist
                frappe.db.sql("SELECT COUNT(*) FROM `tabPPh 21 Settings`")
                pph21_settings_exists = True
            else:
                logger.warning("PPh 21 Settings DocType not found, skipping TER rates migration")
                return False
        except Exception as e:
            logger.warning(f"PPh 21 Settings table not yet created in database: {str(e)}")
            return False

        if not pph21_settings_exists:
            logger.warning("PPh 21 Settings not found, skipping TER rates migration")
            return False

        # Clear existing TER entries to prevent duplicates
        try:
            frappe.db.sql("DELETE FROM `tabPPh 21 TER Table`")
            logger.info("[PI-Install] Successfully cleared existing TER entries")
        except Exception as e:
            logger.warning(f"[PI-Install] Could not clear existing TER entries: {str(e)}")

        # Process each TER category
        count = 0
        for category, rates in ter_rates.items():
            for rate_data in rates:
                try:
                    # Create TER entry
                    ter_entry = frappe.new_doc("PPh 21 TER Table")
                    ter_entry.status_pajak = category
                    ter_entry.income_from = flt(rate_data.get("income_from", 0))
                    ter_entry.income_to = flt(rate_data.get("income_to", 0))
                    ter_entry.rate = flt(rate_data.get("rate", 0))
                    ter_entry.is_highest_bracket = rate_data.get("is_highest_bracket", 0)

                    # Create description
                    if rate_data.get("is_highest_bracket", 0) or rate_data.get("income_to", 0) == 0:
                        description = f"{category} > {flt(rate_data.get('income_from', 0)):,.0f}"
                    else:
                        description = f"{category} {flt(rate_data.get('income_from', 0)):,.0f} - {flt(rate_data.get('income_to', 0)):,.0f}"

                    ter_entry.description = description

                    # Insert with permission bypass
                    ter_entry.flags.ignore_permissions = True
                    ter_entry.flags.ignore_validate = True
                    ter_entry.flags.ignore_mandatory = True
                    ter_entry.insert(ignore_permissions=True)

                    count += 1
                    logger.info(
                        f"[PI-Install] Inserted TER entry for category {category}, income_from={ter_entry.income_from}, income_to={ter_entry.income_to}, rate={ter_entry.rate}"
                    )

                except Exception as e:
                    logger.warning(
                        f"[PI-Install] Error creating TER entry for {category}: {str(e)}"
                    )

        frappe.db.commit()
        logger.info(f"[PI-Install] Successfully migrated {count} TER rates from defaults.json")
        return True

    except Exception as e:
        frappe.db.rollback()
        logger.exception(f"[PI-Install] Error migrating TER rates: {str(e)}")
        return False


def sync_to_bpjs_settings(pi_settings):
    """
    Sync Payroll Indonesia Settings to BPJS Settings

    Args:
        pi_settings: Payroll Indonesia Settings document
    """
    try:
        if frappe.db.exists("DocType", "BPJS Settings") and frappe.db.exists(
            "BPJS Settings", "BPJS Settings"
        ):
            bpjs_settings = frappe.get_doc("BPJS Settings", "BPJS Settings")
            bpjs_fields = [
                "kesehatan_employee_percent",
                "kesehatan_employer_percent",
                "kesehatan_max_salary",
                "jht_employee_percent",
                "jht_employer_percent",
                "jp_employee_percent",
                "jp_employer_percent",
                "jp_max_salary",
                "jkk_percent",
                "jkm_percent",
            ]

            needs_update = False
            changed_fields = []
            for field in bpjs_fields:
                if hasattr(bpjs_settings, field) and hasattr(pi_settings, field):
                    if bpjs_settings.get(field) != pi_settings.get(field):
                        bpjs_settings.set(field, pi_settings.get(field))
                        needs_update = True
                        changed_fields.append(field)

            # Update GL accounts for BPJS if supported
            company = frappe.defaults.get_global_default("company")
            if company and hasattr(bpjs_settings, "accounts"):
                updated_accounts = update_bpjs_gl_accounts(bpjs_settings, company)
                if updated_accounts:
                    needs_update = True
                    changed_fields.append("accounts")

            if needs_update:
                bpjs_settings.flags.ignore_validate = True
                bpjs_settings.flags.ignore_permissions = True
                bpjs_settings.save()
                logger.info(
                    f"[PI-Install] BPJS Settings updated from Payroll Indonesia Settings. Changed fields: {changed_fields}"
                )
    except Exception as e:
        logger.exception(f"[PI-Install] Error syncing to BPJS Settings: {str(e)}")


def update_bpjs_gl_accounts(bpjs_settings, company):
    """
    Update BPJS GL accounts using map_gl_account function

    Args:
        bpjs_settings: BPJS Settings document
        company: Company for which to map accounts

    Returns:
        bool: True if any accounts were updated
    """
    try:
        # Define mapping from BPJS settings account fields to GL account mapper keys
        account_mapping = {
            "kesehatan_account": ("bpjs_kesehatan_payable", "bpjs_payable_accounts"),
            "jht_account": ("bpjs_jht_payable", "bpjs_payable_accounts"),
            "jp_account": ("bpjs_jp_payable", "bpjs_payable_accounts"),
            "jkk_account": ("bpjs_jkk_payable", "bpjs_payable_accounts"),
            "jkm_account": ("bpjs_jkm_payable", "bpjs_payable_accounts"),
            "kesehatan_expense_account": (
                "bpjs_kesehatan_employer_expense",
                "bpjs_expense_accounts",
            ),
            "jht_expense_account": ("bpjs_jht_employer_expense", "bpjs_expense_accounts"),
            "jp_expense_account": ("bpjs_jp_employer_expense", "bpjs_expense_accounts"),
            "jkk_expense_account": ("bpjs_jkk_employer_expense", "bpjs_expense_accounts"),
            "jkm_expense_account": ("bpjs_jkm_employer_expense", "bpjs_expense_accounts"),
        }

        updated = False

        # Update each account field if it exists in the document
        for field_name, (account_key, category) in account_mapping.items():
            if hasattr(bpjs_settings, field_name):
                mapped_account = map_gl_account(company, account_key, category)
                if mapped_account and bpjs_settings.get(field_name) != mapped_account:
                    bpjs_settings.set(field_name, mapped_account)
                    logger.info(
                        f"[PI-Install] Updated BPJS Settings {field_name} to {mapped_account}"
                    )
                    updated = True

        return updated
    except Exception as e:
        logger.warning(f"[PI-Install] Error updating BPJS GL accounts: {str(e)}")
        return False
