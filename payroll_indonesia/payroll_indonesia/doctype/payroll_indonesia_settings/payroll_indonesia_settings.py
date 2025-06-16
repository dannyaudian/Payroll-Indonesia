# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last Modified: 2025-05-24 06:33:36 by dannyaudian

"""
Payroll Indonesia Settings DocType

This module handles configuration settings for Indonesian Payroll processing,
including validation, account mapping, tax settings, and BPJS (social security) settings.
Tax rate calculations are delegated to the PPh 21 TER Table for better data management.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Union, Optional

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now, cint

# Import TER validation only from pph_ter.py
from payroll_indonesia.payroll_indonesia.tax.pph_ter import (
    validate_ter_data_availability,
    map_ptkp_to_ter_category,
)


class PayrollIndonesiaSettings(Document):
    """
    DocType for managing Payroll Indonesia Settings.

    This class handles configuration validation, data syncing between related
    DocTypes, and provides interfaces for retrieving tax rates, PTKP values,
    and GL account configurations for Indonesian payroll processing.
    """

    def validate(self) -> None:
        """
        Validate settings on save.

        Validates all configuration settings for completeness and correctness.
        Skips validation of TER rate fields as they are now managed in the tax module.
        """
        try:
            self.validate_tax_settings()
            self.validate_ter_settings()
            self.validate_bpjs_settings()
            self.validate_json_fields()
            self.validate_parent_account_fields()
            self.update_timestamp()
            self.sync_to_related_doctypes()
        except Exception as e:
            frappe.log_error(
                f"Error validating Payroll Indonesia Settings: {str(e)}", "Settings Error"
            )

    def validate_parent_account_fields(self) -> None:
        """
        Validate parent account candidate fields.

        Ensures the format of parent account fields is correct and validates group accounts.
        """
        # Validate liability account candidates
        if hasattr(self, "default_liability_parents") and self.default_liability_parents:
            try:
                # Check if it's a valid list of accounts
                account_list = self.default_liability_parents.split("\n")
                if not account_list:
                    frappe.msgprint(
                        _("Default liability parent accounts field is not properly formatted"),
                        indicator="orange",
                    )
            except Exception:
                frappe.msgprint(
                    _("Default liability parent accounts field is not properly formatted"),
                    indicator="orange",
                )

        # Validate expense account candidates
        if hasattr(self, "default_expense_parents") and self.default_expense_parents:
            try:
                # Check if it's a valid list of accounts
                account_list = self.default_expense_parents.split("\n")
                if not account_list:
                    frappe.msgprint(
                        _("Default expense parent accounts field is not properly formatted"),
                        indicator="orange",
                    )
            except Exception:
                frappe.msgprint(
                    _("Default expense parent accounts field is not properly formatted"),
                    indicator="orange",
                )

    def update_timestamp(self) -> None:
        """
        Update the timestamp and user info.

        Records the last update time and user for audit purposes.
        """
        self.app_last_updated = now()
        self.app_updated_by = frappe.session.user

    def validate_tax_settings(self) -> None:
        """
        Validate tax-related settings.

        Ensures required tax configuration tables are properly defined.
        """
        if not self.ptkp_table:
            frappe.msgprint(
                _("PTKP values must be defined for tax calculation"), indicator="orange"
            )

        if self.use_ter and not self.ptkp_ter_mapping_table:
            frappe.msgprint(
                _("PTKP to TER mappings should be defined when using TER calculation method"),
                indicator="orange",
            )

        # Validate tax brackets
        if not self.tax_brackets_table:
            frappe.msgprint(
                _("Tax brackets should be defined for tax calculation"), indicator="orange"
            )

    def validate_ter_settings(self) -> None:
        """
        Validate TER-specific settings for completeness.

        Uses the validation function from pph_ter module to check TER configuration.
        """
        if not self.use_ter:
            # If TER is not enabled, no need to validate TER settings
            return

        # Use the validation function from pph_ter.py
        issues = validate_ter_data_availability()
        # Store issues in the field for displaying in the UI
        self.ter_validation_issues = "\n".join(issues) if issues else ""

        # Display comprehensive validation results
        if issues:
            issues_text = "\n• " + "\n• ".join(issues)
            frappe.msgprint(
                _(
                    "TER Configuration Issues Detected:{0}\n\nPlease complete TER setup before using this method for calculations."
                ).format(issues_text),
                indicator="red",
            )

    def validate_bpjs_settings(self) -> None:
        """
        Validate BPJS-related settings.

        Ensures BPJS (social security) percentages are within valid ranges.
        """
        # Validate BPJS percentages
        if self.kesehatan_employee_percent < 0 or self.kesehatan_employee_percent > 5:
            frappe.msgprint(
                _("BPJS Kesehatan employee percentage must be between 0 and 5%"), indicator="orange"
            )

        if self.kesehatan_employer_percent < 0 or self.kesehatan_employer_percent > 10:
            frappe.msgprint(
                _("BPJS Kesehatan employer percentage must be between 0 and 10%"),
                indicator="orange",
            )

    def validate_json_fields(self) -> None:
        """
        Validate JSON fields have valid content.

        Ensures all JSON fields contain valid JSON data.
        """
        json_fields = [
            "bpjs_account_mapping_json",
            "expense_accounts_json",
            "payable_accounts_json",
            "parent_accounts_json",
        ]

        for field in json_fields:
            if hasattr(self, field) and self.get(field):
                try:
                    json.loads(self.get(field))
                except json.JSONDecodeError:
                    frappe.msgprint(
                        _("Invalid JSON format in field {0}").format(field), indicator="red"
                    )
                except Exception:
                    frappe.msgprint(_("Error validating field {0}").format(field), indicator="red")

    def sync_to_related_doctypes(self) -> None:
        """
        Sync settings to related DocTypes.

        Updates BPJS Settings and PPh 21 Settings with relevant values from this DocType.
        """
        try:
            # Sync to BPJS Settings
            self._sync_to_bpjs_settings()

            # Sync to PPh 21 Settings
            self._sync_to_pph_settings()

            # Sync TER rates to PPh 21 TER Table
            self.sync_ter_rates()
        except Exception as e:
            frappe.log_error(f"Error syncing settings: {str(e)}", "Settings Sync Error")

    def _sync_to_bpjs_settings(self) -> None:
        """
        Sync settings to BPJS Settings DocType.

        Internal helper for sync_to_related_doctypes method.
        """
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
            for field in bpjs_fields:
                if (
                    hasattr(bpjs_settings, field)
                    and hasattr(self, field)
                    and bpjs_settings.get(field) != self.get(field)
                ):
                    bpjs_settings.set(field, self.get(field))
                    needs_update = True

            if needs_update:
                bpjs_settings.flags.ignore_validate = True
                bpjs_settings.flags.ignore_permissions = True
                bpjs_settings.save()
                frappe.msgprint(
                    _("BPJS Settings updated from Payroll Indonesia Settings"),
                    indicator="green",
                )

    def _sync_to_pph_settings(self) -> None:
        """
        Sync settings to PPh 21 Settings DocType.

        Internal helper for sync_to_related_doctypes method.
        """
        if frappe.db.exists("DocType", "PPh 21 Settings") and frappe.db.exists(
            "PPh 21 Settings", "PPh 21 Settings"
        ):
            pph_settings = frappe.get_doc("PPh 21 Settings", "PPh 21 Settings")

            # Update calculation method and TER usage flag
            needs_update = False

            if (
                hasattr(pph_settings, "calculation_method")
                and pph_settings.calculation_method != self.tax_calculation_method
            ):
                pph_settings.calculation_method = self.tax_calculation_method
                needs_update = True

            # Sync the use_ter field if it exists in PPh 21 Settings
            if hasattr(pph_settings, "use_ter") and pph_settings.use_ter != self.use_ter:
                pph_settings.use_ter = self.use_ter
                needs_update = True

            if needs_update:
                pph_settings.flags.ignore_validate = True
                pph_settings.flags.ignore_permissions = True
                pph_settings.save()
                frappe.msgprint(
                    _("PPh 21 Settings updated from Payroll Indonesia Settings"),
                    indicator="green",
                )

    def sync_ter_rates(self, force_sync: bool = False) -> None:
        """
        Sync TER rates from JSON fields to PPh 21 TER Table.

        Args:
            force_sync: If True, forces sync even if use_ter is not enabled
        """
        if not frappe.db.exists("DocType", "PPh 21 TER Table"):
            frappe.log_error("PPh 21 TER Table DocType not found - skipping sync", "TER Sync Info")
            return

        # Skip sync if TER is not enabled, unless forced
        if not self.use_ter and not force_sync:
            return

        # Check if table is empty and populate with defaults if needed
        if frappe.db.count("PPh 21 TER Table") == 0:
            try:
                # Import DEFAULT_TER_RATES only where needed to avoid circular imports
                from payroll_indonesia.payroll_indonesia.tax.pph_ter import (
                    DEFAULT_TER_RATES,
                )

                for category, rate in DEFAULT_TER_RATES.items():
                    if not category:
                        continue
                    doc = frappe.new_doc("PPh 21 TER Table")
                    doc.status_pajak = category
                    doc.income_from = 0
                    doc.income_to = 1_000_000_000
                    doc.rate = rate * 100  # Save as percentage
                    doc.is_highest_bracket = 1
                    doc.insert()
                frappe.msgprint(_("Default TER data has been inserted."))
                return
            except Exception as e:
                frappe.log_error(f"Error inserting default TER rates: {str(e)}", "TER Sync Error")

        # Proceed with normal sync if table is not empty
        try:
            # Track sync status
            success_count = 0
            error_count = 0

            # Sync TER A rates
            if self.ter_rate_ter_a_json:
                try:
                    ter_a_rates = json.loads(self.ter_rate_ter_a_json)
                    success_a = self._sync_ter_category_rates("TER A", ter_a_rates)
                    success_count += success_a
                except Exception as e:
                    error_count += 1
                    frappe.log_error(f"Error syncing TER A rates: {str(e)}", "TER Sync Error")

            # Sync TER B rates
            if self.ter_rate_ter_b_json:
                try:
                    ter_b_rates = json.loads(self.ter_rate_ter_b_json)
                    success_b = self._sync_ter_category_rates("TER B", ter_b_rates)
                    success_count += success_b
                except Exception as e:
                    error_count += 1
                    frappe.log_error(f"Error syncing TER B rates: {str(e)}", "TER Sync Error")

            # Sync TER C rates
            if self.ter_rate_ter_c_json:
                try:
                    ter_c_rates = json.loads(self.ter_rate_ter_c_json)
                    success_c = self._sync_ter_category_rates("TER C", ter_c_rates)
                    success_count += success_c
                except Exception as e:
                    error_count += 1
                    frappe.log_error(f"Error syncing TER C rates: {str(e)}", "TER Sync Error")

            # Log sync results if performed through forced sync
            if force_sync:
                if error_count > 0:
                    frappe.msgprint(
                        _("TER Rates sync completed with some errors. See error log for details."),
                        indicator="orange",
                    )
                else:
                    frappe.msgprint(
                        _("TER Rates successfully synced to database."), indicator="green"
                    )

        except Exception as e:
            frappe.log_error(f"Error in sync_ter_rates: {str(e)}", "TER Sync Error")

    def _sync_ter_category_rates(self, category: str, rates: List[Dict]) -> int:
        """
        Sync rates for a specific TER category.

        Args:
            category: TER category name ("TER A", "TER B", "TER C")
            rates: List of rate dictionaries

        Returns:
            int: Number of successfully synced records
        """
        if not isinstance(rates, list):
            return 0

        success_count = 0
        for rate_data in rates:
            try:
                # Skip invalid entries
                if not isinstance(rate_data, dict):
                    continue

                income_from = flt(rate_data.get("income_from", 0))
                income_to = flt(rate_data.get("income_to", 0))
                rate = flt(rate_data.get("rate", 0))
                is_highest_bracket = bool(rate_data.get("is_highest_bracket", 0))

                filters = {
                    "status_pajak": category,
                    "income_from": income_from,
                    "income_to": income_to,
                }

                if frappe.db.exists("PPh 21 TER Table", filters):
                    # Update existing record
                    ter_doc = frappe.get_doc("PPh 21 TER Table", filters)
                    ter_doc.rate = rate
                    ter_doc.is_highest_bracket = is_highest_bracket
                    ter_doc.flags.ignore_permissions = True
                    ter_doc.save()
                    success_count += 1
                else:
                    # Create new record
                    ter_doc = frappe.new_doc("PPh 21 TER Table")
                    ter_doc.update(
                        {
                            "status_pajak": category,
                            "income_from": income_from,
                            "income_to": income_to,
                            "rate": rate,
                            "is_highest_bracket": is_highest_bracket,
                            "description": self._build_ter_description(category, rate_data),
                        }
                    )
                    ter_doc.flags.ignore_permissions = True
                    ter_doc.insert()
                    success_count += 1
            except Exception as e:
                frappe.log_error(
                    f"Error syncing TER rate record for {category}: {str(e)}", "TER Rate Sync Error"
                )

        return success_count

    def _build_ter_description(self, status: str, rate_data: Dict) -> str:
        """
        Build description for TER rates.

        Args:
            status: TER category
            rate_data: Rate data dictionary

        Returns:
            str: Human-readable description of the rate
        """
        income_from = flt(rate_data.get("income_from", 0))
        income_to = flt(rate_data.get("income_to", 0))

        if rate_data.get("is_highest_bracket") or income_to == 0:
            return f"{status} > {income_from:,.0f}"
        else:
            return f"{status} {income_from:,.0f} – {income_to:,.0f}"

    def get_ptkp_value(self, status_pajak: str) -> float:
        """
        Get PTKP value for a specific tax status.

        Args:
            status_pajak: PTKP tax status code

        Returns:
            float: The PTKP amount for the given status
        """
        if not self.ptkp_table:
            return 0

        for row in self.ptkp_table:
            if row.status_pajak == status_pajak:
                return flt(row.ptkp_amount)

        return 0

    def get_ptkp_values_dict(self) -> Dict[str, float]:
        """
        Return PTKP values as a dictionary.

        Returns:
            Dict[str, float]: Dictionary mapping PTKP status codes to amounts
        """
        ptkp_dict: Dict[str, float] = {}
        if hasattr(self, "ptkp_table") and self.ptkp_table:
            for row in self.ptkp_table:
                ptkp_dict[row.status_pajak] = flt(row.ptkp_amount)
        return ptkp_dict

    def get_ptkp_ter_mapping_dict(self) -> Dict[str, str]:
        """
        Return PTKP to TER mapping as a dictionary.

        Returns:
            Dict[str, str]: Dictionary mapping PTKP status codes to TER categories
        """
        mapping_dict: Dict[str, str] = {}
        if hasattr(self, "ptkp_ter_mapping_table") and self.ptkp_ter_mapping_table:
            for row in self.ptkp_ter_mapping_table:
                mapping_dict[row.ptkp_status] = row.ter_category
        return mapping_dict

    def get_tax_brackets_list(self) -> List[Dict[str, float]]:
        """
        Return tax brackets as a list of dictionaries.

        Returns:
            List[Dict[str, float]]: List of tax bracket configurations
        """
        brackets: List[Dict[str, float]] = []
        if hasattr(self, "tax_brackets_table") and self.tax_brackets_table:
            for row in self.tax_brackets_table:
                brackets.append(
                    {
                        "income_from": flt(row.income_from),
                        "income_to": flt(row.income_to),
                        "tax_rate": flt(row.tax_rate),
                    }
                )
        return brackets

    def get_tipe_karyawan_list(self) -> List[str]:
        """
        Return employee types as a list.

        Returns:
            List[str]: List of employee type names
        """
        types: List[str] = []
        try:
            if hasattr(self, "tipe_karyawan") and self.tipe_karyawan:
                for row in self.tipe_karyawan:
                    types.append(row.tipe_karyawan)

            # If still empty, try to load from defaults.json
            if not types:
                types = self._get_default_tipe_karyawan()
        except Exception as e:
            frappe.log_error(f"Error getting tipe_karyawan list: {str(e)}", "Settings Error")

        return types

    def _get_default_tipe_karyawan(self) -> List[str]:
        """
        Get default employee types from defaults.json as fallback.

        Returns:
            List[str]: Default employee type names
        """
        try:
            from pathlib import Path
            import json

            defaults: List[str] = []
            # Try to get app path
            app_path = frappe.get_app_path("payroll_indonesia")
            defaults_file = Path(app_path) / "config" / "defaults.json"

            if defaults_file.exists():
                with open(defaults_file, "r") as f:
                    config = json.load(f)
                if "tipe_karyawan" in config:
                    defaults = config["tipe_karyawan"]

            return defaults
        except Exception:
            return ["Tetap", "Tidak Tetap", "Freelance"]  # Hardcoded fallback

    def get_ter_category(self, ptkp_status: str) -> str:
        """
        Get TER category for a specific PTKP status.

        Args:
            ptkp_status: PTKP status code (e.g., 'TK0', 'K1')

        Returns:
            str: The corresponding TER category ('TER A', 'TER B', or 'TER C')
        """
        # Validate input
        if not ptkp_status:
            return "TER C"  # Default to highest category for safety

        # Normalize the status
        try:
            ptkp_status = str(ptkp_status).strip().upper()
        except Exception:
            return "TER C"  # Default on error

        # First try to get mapping from settings
        if hasattr(self, "ptkp_ter_mapping_table") and self.ptkp_ter_mapping_table:
            for row in self.ptkp_ter_mapping_table:
                if hasattr(row, "ptkp_status") and row.ptkp_status == ptkp_status:
                    return row.ter_category

        # If no mapping found, use the function from pph_ter.py
        return map_ptkp_to_ter_category(ptkp_status)

    def get_ter_rate(
        self, ter_category: str, income: Union[float, int, str], debug: bool = False
    ) -> float:
        """
        Get TER rate based on TER category and income.

        This method queries the PPh 21 TER Table to find the appropriate tax rate
        based on income level and TER category.

        Args:
            ter_category: TER category ('TER A', 'TER B', 'TER C')
            income: Monthly income amount
            debug: If True, log debug information

        Returns:
            float: The TER rate as a decimal (e.g., 0.15 for 15%)

        Note:
            This method is deprecated. Use PPh 21 TER Table directly in future versions.
        """
        # Log deprecation warning
        logger = frappe.logger("payroll_indonesia")
        logger.warning(
            "PayrollIndonesiaSettings.get_ter_rate() is deprecated. "
            "Use PPh 21 TER Table directly in future versions."
        )

        # Early validation
        if not self.use_ter:
            return 0

        # Validate inputs
        if not ter_category or not isinstance(ter_category, str):
            frappe.throw(_("TER category must be specified"))

        # Ensure income is a valid number
        try:
            income_value = flt(income)
            if income_value < 0:
                frappe.throw(_("Income cannot be negative"))
        except (ValueError, TypeError):
            frappe.throw(_("Income must be a valid number"))

        # Default rates by category - fallback values if database lookup fails
        default_rates = {
            "TER A": 0.05,  # 5%
            "TER B": 0.15,  # 15%
            "TER C": 0.25,  # 25%
        }

        try:
            # First check for highest bracket that matches
            highest_bracket = frappe.get_all(
                "PPh 21 TER Table",
                filters={
                    "status_pajak": ter_category,
                    "is_highest_bracket": 1,
                    "income_from": ["<=", income_value],
                },
                fields=["rate"],
                order_by="income_from desc",
                limit=1,
            )

            if highest_bracket:
                rate = flt(highest_bracket[0].rate) / 100.0  # Convert percentage to decimal
                if debug:
                    logger.debug(
                        {
                            "message": "TER rate calculation (highest bracket)",
                            "category": ter_category,
                            "income": income_value,
                            "rate": rate,
                            "source": "database",
                        }
                    )
                return rate

            # If no highest bracket found, look for range bracket
            range_brackets = frappe.get_all(
                "PPh 21 TER Table",
                filters={
                    "status_pajak": ter_category,
                    "income_from": ["<=", income_value],
                    "income_to": [">", income_value],
                },
                fields=["rate"],
                order_by="income_from desc",
                limit=1,
            )

            if range_brackets:
                rate = flt(range_brackets[0].rate) / 100.0  # Convert percentage to decimal
                if debug:
                    logger.debug(
                        {
                            "message": "TER rate calculation (range bracket)",
                            "category": ter_category,
                            "income": income_value,
                            "rate": rate,
                            "source": "database",
                        }
                    )
                return rate

            # If no brackets found, use default rates
            rate = default_rates.get(ter_category, 0.25)
            if debug:
                logger.debug(
                    {
                        "message": "TER rate calculation (default)",
                        "category": ter_category,
                        "income": income_value,
                        "rate": rate,
                        "source": "default",
                    }
                )
            return rate

        except Exception as e:
            # Log error and return default rate
            logger.error(f"Error getting TER rate: {str(e)}")
            default_rate = default_rates.get(ter_category, 0.25)
            if debug:
                logger.debug(
                    {
                        "message": "TER rate calculation (error fallback)",
                        "category": ter_category,
                        "income": income_value,
                        "rate": default_rate,
                        "error": str(e),
                    }
                )
            return default_rate

    def ensure_ter_setup_complete(self) -> Dict[str, Any]:
        """
        Check if TER setup is complete and ready for tax calculations.

        Returns:
            Dict[str, Any]: Status of TER setup with details
        """
        result: Dict[str, Any] = {
            "is_complete": False,
            "issues": [],
            "use_ter": self.use_ter,
        }

        # First check if TER is even enabled
        if not self.use_ter:
            result["is_complete"] = False
            result["issues"].append(_("TER calculation method is not enabled"))
            return result

        # Check if PTKP to TER mapping is complete
        if not self.ptkp_ter_mapping_table or len(self.ptkp_ter_mapping_table) == 0:
            result["issues"].append(_("PTKP to TER mapping is missing"))

        # Check if PPh 21 TER Table (database table) has entries
        try:
            ter_table_count = frappe.db.count("PPh 21 TER Table")
            if ter_table_count == 0:
                result["issues"].append(_("PPh 21 TER Table is empty"))
        except Exception:
            result["issues"].append(_("Could not verify PPh 21 TER Table status"))

        # Set overall status
        result["is_complete"] = len(result["issues"]) == 0

        return result

    def get_gl_account_config(self) -> Dict[str, Any]:
        """
        Return GL account configurations as a dictionary.

        Returns:
            Dict[str, Any]: GL account configurations for various payroll transactions
        """
        config: Dict[str, Any] = {}

        # Add BPJS account mapping
        if self.bpjs_account_mapping_json:
            try:
                config["bpjs_account_mapping"] = json.loads(self.bpjs_account_mapping_json)
            except Exception:
                frappe.log_error("Invalid JSON in BPJS account mapping", "GL Config Error")

        # Add expense accounts
        if self.expense_accounts_json:
            try:
                config["expense_accounts"] = json.loads(self.expense_accounts_json)
            except Exception:
                frappe.log_error("Invalid JSON in expense accounts", "GL Config Error")

        # Add payable accounts
        if self.payable_accounts_json:
            try:
                config["payable_accounts"] = json.loads(self.payable_accounts_json)
            except Exception:
                frappe.log_error("Invalid JSON in payable accounts", "GL Config Error")

        # Add parent accounts
        if self.parent_accounts_json:
            try:
                config["parent_accounts"] = json.loads(self.parent_accounts_json)
            except Exception:
                frappe.log_error("Invalid JSON in parent accounts", "GL Config Error")

        # Add parent account candidates
        config["parent_account_candidates"] = {
            "liability": self.get_parent_account_candidates_liability(),
            "expense": self.get_parent_account_candidates_expense(),
        }

        return config

    def get_parent_account_candidates_liability(self) -> List[str]:
        """
        Get list of valid parent account candidates for liability accounts.

        This function returns a list of account names that can be used as
        parent accounts for liability type accounts. It validates that only
        group accounts are included in the returned list.

        Returns:
            List[str]: List of valid liability parent account names
        """
        # Default fallback candidates if none defined
        default_candidates = ["Duties and Taxes", "Current Liabilities", "Accounts Payable"]

        # If no field defined, return defaults
        if not hasattr(self, "default_liability_parents") or not self.default_liability_parents:
            return default_candidates

        # Parse the field value (expected format is one account name per line)
        candidates = []
        for line in self.default_liability_parents.split("\n"):
            account_name = line.strip()
            if account_name:
                candidates.append(account_name)

        # If no valid candidates found, return defaults
        if not candidates:
            return default_candidates

        # Validate that each account exists and is a group account
        valid_candidates = []
        for account_name in candidates:
            # For each company, check if this account exists and is a group
            companies = frappe.get_all("Company", pluck="name")
            for company in companies:
                # Try with company suffix
                abbr = frappe.get_cached_value("Company", company, "abbr") or ""
                account_with_suffix = f"{account_name} - {abbr}" if abbr else account_name

                # Check if account exists with suffix
                if frappe.db.exists("Account", account_with_suffix):
                    is_group = cint(frappe.db.get_value("Account", account_with_suffix, "is_group"))
                    if is_group:
                        if account_name not in valid_candidates:
                            valid_candidates.append(account_name)

                # Also check without suffix
                filters = {"account_name": account_name, "company": company, "is_group": 1}
                if frappe.db.exists("Account", filters):
                    if account_name not in valid_candidates:
                        valid_candidates.append(account_name)

        # If no valid group accounts found, return defaults
        if not valid_candidates:
            return default_candidates

        return valid_candidates

    def get_parent_account_candidates_expense(self) -> List[str]:
        """
        Get list of valid parent account candidates for expense accounts.

        This function returns a list of account names that can be used as
        parent accounts for expense type accounts. It validates that only
        group accounts are included in the returned list.

        Returns:
            List[str]: List of valid expense parent account names
        """
        # Default fallback candidates if none defined
        default_candidates = ["Direct Expenses", "Indirect Expenses", "Expenses"]

        # If no field defined, return defaults
        if not hasattr(self, "default_expense_parents") or not self.default_expense_parents:
            return default_candidates

        # Parse the field value (expected format is one account name per line)
        candidates = []
        for line in self.default_expense_parents.split("\n"):
            account_name = line.strip()
            if account_name:
                candidates.append(account_name)

        # If no valid candidates found, return defaults
        if not candidates:
            return default_candidates

        # Validate that each account exists and is a group account
        valid_candidates = []
        for account_name in candidates:
            # For each company, check if this account exists and is a group
            companies = frappe.get_all("Company", pluck="name")
            for company in companies:
                # Try with company suffix
                abbr = frappe.get_cached_value("Company", company, "abbr") or ""
                account_with_suffix = f"{account_name} - {abbr}" if abbr else account_name

                # Check if account exists with suffix
                if frappe.db.exists("Account", account_with_suffix):
                    is_group = cint(frappe.db.get_value("Account", account_with_suffix, "is_group"))
                    if is_group:
                        if account_name not in valid_candidates:
                            valid_candidates.append(account_name)

                # Also check without suffix
                filters = {"account_name": account_name, "company": company, "is_group": 1}
                if frappe.db.exists("Account", filters):
                    if account_name not in valid_candidates:
                        valid_candidates.append(account_name)

        # If no valid group accounts found, return defaults
        if not valid_candidates:
            return default_candidates

        return valid_candidates

    def on_update(self) -> None:
        """
        Perform actions after document is updated.

        Populates default values if needed.
        """
        self.populate_default_values()

        # Ensure we have tipe_karyawan
        if not self.tipe_karyawan or len(self.tipe_karyawan) == 0:
            self.populate_tipe_karyawan()

    def populate_tipe_karyawan(self) -> None:
        """
        Populate tipe karyawan from defaults.json if empty.

        Adds default employee types to the system.
        """
        try:
            if (
                not hasattr(self, "tipe_karyawan")
                or not self.tipe_karyawan
                or len(self.tipe_karyawan) == 0
            ):
                # Get default values
                default_types = self._get_default_tipe_karyawan()

                if default_types:
                    # Create child table entries
                    for tipe in default_types:
                        row = self.append("tipe_karyawan", {})
                        row.tipe_karyawan = tipe

                    # Save changes
                    self.db_update()
                    frappe.logger("payroll_indonesia").info("Populated default tipe karyawan")
        except Exception as e:
            frappe.log_error(f"Error populating tipe karyawan: {str(e)}", "Settings Error")

    def populate_default_values(self) -> None:
        """
        Populate default values from defaults.json if fields are empty.

        Loads defaults for tax settings, employee types, and account mappings.
        """
        try:
            # Only populated if field values are empty
            defaults_loaded = False

            # Check if Tipe Karyawan Entry DocType exists and try to create if missing
            if not frappe.db.exists("DocType", "Tipe Karyawan Entry"):
                try:
                    self._ensure_child_doctypes_exist()
                except Exception as e:
                    frappe.log_error(
                        f"Error ensuring child DocTypes exist: {str(e)}", "Settings Error"
                    )

            # Load config/defaults.json
            try:
                from pathlib import Path
                import json

                # Try to get app path
                app_path = frappe.get_app_path("payroll_indonesia")
                defaults_file = Path(app_path) / "config" / "defaults.json"

                if defaults_file.exists():
                    with open(defaults_file, "r") as f:
                        defaults = json.load(f)

                    # Populate TER rates if empty
                    if (
                        not self.ter_rate_ter_a_json
                        and "ter_rates" in defaults
                        and "TER A" in defaults["ter_rates"]
                    ):
                        self.ter_rate_ter_a_json = json.dumps(
                            defaults["ter_rates"]["TER A"], indent=2
                        )
                        defaults_loaded = True

                    if (
                        not self.ter_rate_ter_b_json
                        and "ter_rates" in defaults
                        and "TER B" in defaults["ter_rates"]
                    ):
                        self.ter_rate_ter_b_json = json.dumps(
                            defaults["ter_rates"]["TER B"], indent=2
                        )
                        defaults_loaded = True

                    if (
                        not self.ter_rate_ter_c_json
                        and "ter_rates" in defaults
                        and "TER C" in defaults["ter_rates"]
                    ):
                        self.ter_rate_ter_c_json = json.dumps(
                            defaults["ter_rates"]["TER C"], indent=2
                        )
                        defaults_loaded = True

                    # Populate GL accounts if empty
                    if (
                        not self.bpjs_account_mapping_json
                        and "gl_accounts" in defaults
                        and "bpjs_account_mapping" in defaults["gl_accounts"]
                    ):
                        self.bpjs_account_mapping_json = json.dumps(
                            defaults["gl_accounts"]["bpjs_account_mapping"], indent=2
                        )
                        defaults_loaded = True

                    if (
                        not self.expense_accounts_json
                        and "gl_accounts" in defaults
                        and "expense_accounts" in defaults["gl_accounts"]
                    ):
                        self.expense_accounts_json = json.dumps(
                            defaults["gl_accounts"]["expense_accounts"], indent=2
                        )
                        defaults_loaded = True

                    if (
                        not self.payable_accounts_json
                        and "gl_accounts" in defaults
                        and "payable_accounts" in defaults["gl_accounts"]
                    ):
                        self.payable_accounts_json = json.dumps(
                            defaults["gl_accounts"]["payable_accounts"], indent=2
                        )
                        defaults_loaded = True

                    if (
                        not self.parent_accounts_json
                        and "gl_accounts" in defaults
                        and "parent_accounts" in defaults["gl_accounts"]
                    ):
                        self.parent_accounts_json = json.dumps(
                            defaults["gl_accounts"]["parent_accounts"], indent=2
                        )
                        defaults_loaded = True

                    # Populate parent account candidates if empty
                    if (
                        not self.default_liability_parents
                        and "gl_accounts" in defaults
                        and "parent_account_candidates" in defaults["gl_accounts"]
                        and "liability" in defaults["gl_accounts"]["parent_account_candidates"]
                    ):
                        self.default_liability_parents = "\n".join(
                            defaults["gl_accounts"]["parent_account_candidates"]["liability"]
                        )
                        defaults_loaded = True

                    if (
                        not self.default_expense_parents
                        and "gl_accounts" in defaults
                        and "parent_account_candidates" in defaults["gl_accounts"]
                        and "expense" in defaults["gl_accounts"]["parent_account_candidates"]
                    ):
                        self.default_expense_parents = "\n".join(
                            defaults["gl_accounts"]["parent_account_candidates"]["expense"]
                        )
                        defaults_loaded = True

                    # Populate PTKP table if empty
                    if hasattr(self, "ptkp_table") and (
                        not self.ptkp_table or len(self.ptkp_table) == 0
                    ):
                        if "ptkp" in defaults:
                            # Clear existing rows if any
                            self.set("ptkp_table", [])

                            for status, amount in defaults["ptkp"].items():
                                row = self.append("ptkp_table", {})
                                row.status_pajak = status
                                row.ptkp_amount = amount

                            defaults_loaded = True

                    # Populate PTKP to TER mapping if empty
                    if hasattr(self, "ptkp_ter_mapping_table") and (
                        not self.ptkp_ter_mapping_table or len(self.ptkp_ter_mapping_table) == 0
                    ):
                        if "ptkp_to_ter_mapping" in defaults:
                            # Clear existing rows if any
                            self.set("ptkp_ter_mapping_table", [])

                            for status, category in defaults["ptkp_to_ter_mapping"].items():
                                row = self.append("ptkp_ter_mapping_table", {})
                                row.ptkp_status = status
                                row.ter_category = category

                            defaults_loaded = True

                    # Populate tax brackets if empty
                    if hasattr(self, "tax_brackets_table") and (
                        not self.tax_brackets_table or len(self.tax_brackets_table) == 0
                    ):
                        if "tax_brackets" in defaults:
                            # Clear existing rows if any
                            self.set("tax_brackets_table", [])

                            for bracket in defaults["tax_brackets"]:
                                row = self.append("tax_brackets_table", {})
                                row.income_from = bracket.get("income_from", 0)
                                row.income_to = bracket.get("income_to", 0)
                                row.tax_rate = bracket.get("tax_rate", 0)

                            defaults_loaded = True

                    # Populate tipe karyawan if empty
                    if hasattr(self, "tipe_karyawan") and (
                        not self.tipe_karyawan or len(self.tipe_karyawan) == 0
                    ):
                        if "tipe_karyawan" in defaults:
                            # Clear existing rows if any
                            self.set("tipe_karyawan", [])

                            for tipe in defaults["tipe_karyawan"]:
                                row = self.append("tipe_karyawan", {})
                                row.tipe_karyawan = tipe

                            defaults_loaded = True

                    # If defaults were loaded, save the document
                    if defaults_loaded:
                        self.db_update()
                        frappe.msgprint(
                            _("Default values loaded from config/defaults.json"), indicator="green"
                        )

            except Exception as e:
                frappe.log_error(f"Error loading defaults.json: {str(e)}", "Settings Error")

        except Exception as e:
            frappe.log_error(f"Error populating default values: {str(e)}", "Settings Error")

    def _ensure_child_doctypes_exist(self) -> None:
        """
        Ensure all required child DocTypes exist, try to create them if missing.

        Creates child DocTypes needed for settings tables if they don't exist.
        """
        # Dictionary of DocTypes to check/create with their fields
        child_doctypes = {
            "Tipe Karyawan Entry": [
                {
                    "fieldname": "tipe_karyawan",
                    "fieldtype": "Data",
                    "label": "Tipe Karyawan",
                    "in_list_view": 1,
                    "reqd": 1,
                }
            ],
            "PTKP Table Entry": [
                {
                    "fieldname": "status_pajak",
                    "fieldtype": "Data",
                    "label": "PTKP Status",
                    "in_list_view": 1,
                    "reqd": 1,
                },
                {
                    "fieldname": "ptkp_amount",
                    "fieldtype": "Currency",
                    "label": "PTKP Amount",
                    "in_list_view": 1,
                    "reqd": 1,
                    "default": 0.0,
                },
            ],
            "Tax Bracket Entry": [
                {
                    "fieldname": "income_from",
                    "fieldtype": "Currency",
                    "label": "Income From",
                    "in_list_view": 1,
                    "reqd": 1,
                    "default": 0.0,
                },
                {
                    "fieldname": "income_to",
                    "fieldtype": "Currency",
                    "label": "Income To",
                    "in_list_view": 1,
                    "reqd": 1,
                    "default": 0.0,
                },
                {
                    "fieldname": "tax_rate",
                    "fieldtype": "Float",
                    "label": "Tax Rate (%)",
                    "in_list_view": 1,
                    "reqd": 1,
                    "default": 0.0,
                    "precision": 2,
                },
            ],
            "PTKP TER Mapping Entry": [
                {
                    "fieldname": "ptkp_status",
                    "fieldtype": "Data",
                    "label": "PTKP Status",
                    "in_list_view": 1,
                    "reqd": 1,
                },
                {
                    "fieldname": "ter_category",
                    "fieldtype": "Select",
                    "label": "TER Category",
                    "options": "TER A\nTER B\nTER C",
                    "in_list_view": 1,
                    "reqd": 1,
                },
            ],
        }

        # Check and create each missing DocType
        for doctype_name, fields in child_doctypes.items():
            if not frappe.db.exists("DocType", doctype_name):
                try:
                    # Create new DocType
                    doctype = frappe.new_doc("DocType")
                    doctype.name = doctype_name
                    doctype.module = "Payroll Indonesia"
                    doctype.istable = 1
                    doctype.editable_grid = 1

                    # Add all fields to the DocType
                    for field_def in fields:
                        doctype.append("fields", field_def)

                    # Insert with admin privileges
                    doctype.flags.ignore_permissions = True
                    doctype.insert(ignore_permissions=True)
                    frappe.db.commit()

                    # Log successful creation
                    frappe.logger("payroll_indonesia").info(
                        f"Successfully created missing DocType: {doctype_name}"
                    )

                except Exception as e:
                    # Log detailed error information
                    frappe.log_error(
                        message=f"Failed to create DocType {doctype_name}: {str(e)}",
                        title="Setup Error",
                    )
