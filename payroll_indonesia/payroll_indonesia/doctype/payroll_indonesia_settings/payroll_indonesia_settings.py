# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Payroll Indonesia Settings DocType Controller

This module handles configuration settings for Indonesian Payroll processing,
delegating validation to central validation helpers and syncing with configuration.
"""

import json
import logging
from typing import Dict, List, Optional, Union, Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint, now, get_site_path

from payroll_indonesia.payroll_indonesia.validations import validate_bpjs_components
from payroll_indonesia.payroll_indonesia import utils

# Configure logger
logger = logging.getLogger(__name__)


def on_update(doc, method=None):
    """
    Hook function for doc_events to sync settings to defaults.json if enabled.

    Args:
        doc: The document instance being updated
        method: The method that triggered this hook (unused)
    """
    original_creation = frappe.db.get_value(doc.doctype, doc.name, "creation")
    if doc.sync_to_defaults:
        utils.write_json_file_if_enabled(doc)
    if original_creation and doc.creation != original_creation:
        logger.warning(
            f"Creation timestamp mismatch for {doc.name}. Resetting to original value"
        )
        doc.creation = original_creation


class PayrollIndonesiaSettings(Document):
    """
    DocType for managing Payroll Indonesia Settings.

    This class handles configuration validation, data syncing between related
    DocTypes, and interfaces with the central configuration system.
    """

    def validate(self) -> None:
        """
        Validate settings on save.

        Delegates validation to central validation helpers and performs minimal
        local validation for configuration integrity.
        """
        try:
            # Update timestamp for audit
            self.app_last_updated = now()
            self.app_updated_by = frappe.session.user

            # Perform validations
            self._validate_tax_settings()
            self._validate_bpjs_settings()
            self._validate_ter_settings()
            self._validate_ptkp_ter_mapping()

            # Sync settings to related doctypes
            self._sync_to_related_doctypes()

            logger.info(f"Validated Payroll Indonesia Settings by {self.app_updated_by}")

        except Exception as e:
            logger.error(f"Error validating Payroll Indonesia Settings: {str(e)}")
            frappe.log_error(
                f"Error validating Payroll Indonesia Settings: {str(e)}", "Settings Error"
            )

    def on_update(self) -> None:
        """
        Perform actions after document is updated.

        Syncs settings to defaults.json if enabled.
        """
        original_creation = frappe.db.get_value(self.doctype, self.name, "creation")
        if self.sync_to_defaults:
            utils.write_json_file_if_enabled(self)

        if original_creation and self.creation != original_creation:
            logger.warning(
                f"Creation timestamp mismatch for {self.name}. Resetting to original value"
            )
            self.creation = original_creation

    def _validate_tax_settings(self) -> None:
        """
        Validate tax-related settings.

        Ensures required tax configuration tables are properly defined.
        """
        # Validate PTKP table
        if not self.ptkp_table:
            frappe.msgprint(
                _("PTKP values must be defined for tax calculation"), indicator="orange"
            )

        # Validate tax brackets for progressive calculation
        if self.tax_calculation_method == "Progressive" and not self.tax_brackets_table:
            frappe.msgprint(
                _("Tax brackets must be defined for Progressive tax calculation"),
                indicator="red",
            )

        # Validate biaya jabatan percent is within limits (typically 0-10%)
        if hasattr(self, "biaya_jabatan_percent"):
            if self.biaya_jabatan_percent < 0 or self.biaya_jabatan_percent > 10:
                frappe.msgprint(
                    _("Biaya Jabatan percentage must be between 0% and 10%"),
                    indicator="orange",
                )

    def _validate_bpjs_settings(self) -> None:
        """
        Validate BPJS-related settings.

        Ensures BPJS percentages are within valid ranges.
        """
        # BPJS Kesehatan validation (typically 1% employee, 4% employer)
        if self.kesehatan_employee_percent < 0 or self.kesehatan_employee_percent > 5:
            frappe.msgprint(
                _("BPJS Kesehatan employee percentage must be between 0% and 5%"),
                indicator="orange",
            )

        if self.kesehatan_employer_percent < 0 or self.kesehatan_employer_percent > 10:
            frappe.msgprint(
                _("BPJS Kesehatan employer percentage must be between 0% and 10%"),
                indicator="orange",
            )

        # JHT validation (typically 2% employee, 3.7% employer)
        if self.jht_employee_percent < 0 or self.jht_employee_percent > 5:
            frappe.msgprint(
                _("BPJS JHT employee percentage must be between 0% and 5%"),
                indicator="orange",
            )

        if self.jht_employer_percent < 0 or self.jht_employer_percent > 10:
            frappe.msgprint(
                _("BPJS JHT employer percentage must be between 0% and 10%"),
                indicator="orange",
            )

        # JP validation (typically 1% employee, 2% employer)
        if self.jp_employee_percent < 0 or self.jp_employee_percent > 5:
            frappe.msgprint(
                _("BPJS JP employee percentage must be between 0% and 5%"),
                indicator="orange",
            )

        if self.jp_employer_percent < 0 or self.jp_employer_percent > 10:
            frappe.msgprint(
                _("BPJS JP employer percentage must be between 0% and 10%"),
                indicator="orange",
            )

        # Validate BPJS components existence
        if self.company and frappe.db.table_exists("Salary Component"):
            try:
                validate_bpjs_components(self.company)
            except Exception as e:
                logger.warning(f"BPJS component validation warning: {str(e)}")
                frappe.msgprint(str(e), indicator="orange")

    def _validate_ter_settings(self) -> None:
        """
        Validate TER-related settings.

        Ensures TER rate table is properly defined when using TER calculation.
        """
        if self.tax_calculation_method == "TER":
            if not self.ter_rate_table:
                frappe.msgprint(
                    _("TER rate table must be defined when using TER calculation method"),
                    indicator="red",
                )

            # Validate TER fallback rate
            if self.ter_fallback_rate < 0 or self.ter_fallback_rate > 100:
                frappe.msgprint(
                    _("TER fallback rate must be between 0% and 100%"),
                    indicator="orange",
                )

            # Check if all three TER categories (A, B, C) have entries
            ter_categories = {row.status_pajak for row in self.ter_rate_table}
            expected_categories = {"TER A", "TER B", "TER C"}
            missing_categories = expected_categories - ter_categories

            if missing_categories:
                frappe.msgprint(
                    _("Missing TER rate entries for categories: {0}").format(
                        ", ".join(missing_categories)
                    ),
                    indicator="orange",
                )

    def _validate_ptkp_ter_mapping(self) -> None:
        """
        Validate PTKP to TER mapping.

        Ensures all PTKP values have corresponding TER mappings when using TER calculation.
        """
        if self.tax_calculation_method == "TER":
            # Get all PTKP status codes
            ptkp_codes = {row.status_pajak for row in self.ptkp_table}

            # Get all mapped PTKP status codes
            mapped_ptkp_codes = {row.ptkp_status for row in self.ptkp_ter_mapping_table}

            # Find unmapped PTKP codes
            unmapped_codes = ptkp_codes - mapped_ptkp_codes

            if unmapped_codes:
                frappe.msgprint(
                    _(
                        "The following PTKP status codes are not mapped to TER categories: {0}"
                    ).format(", ".join(unmapped_codes)),
                    indicator="orange",
                )

    def _sync_to_related_doctypes(self) -> None:
        """
        Sync settings to related DocTypes.

        Updates BPJS Settings and PPh 21 Settings with relevant values from this DocType.
        """
        # Sync to BPJS Settings
        self._sync_to_bpjs_settings()

        # Sync to PPh 21 Settings
        self._sync_to_pph_settings()

        logger.info("Synced settings to related DocTypes")

    def _sync_to_bpjs_settings(self) -> None:
        """
        Sync settings to BPJS Settings DocType.

        Internal helper for sync_to_related_doctypes method.
        """
        if not frappe.db.table_exists("BPJS Settings"):
            return

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
        if not frappe.db.table_exists("PPh 21 Settings"):
            return

        if frappe.db.exists("DocType", "PPh 21 Settings") and frappe.db.exists(
            "PPh 21 Settings", "PPh 21 Settings"
        ):
            pph_settings = frappe.get_doc("PPh 21 Settings", "PPh 21 Settings")

            # Field mapping between this DocType and PPh 21 Settings
            field_mapping = {
                "tax_calculation_method": "calculation_method",
                "use_ter": "use_ter",
                "use_gross_up": "use_gross_up",
                "biaya_jabatan_percent": "biaya_jabatan_percent",
                "biaya_jabatan_max": "biaya_jabatan_max",
                "npwp_mandatory": "npwp_mandatory",
            }

            needs_update = False
            for our_field, pph_field in field_mapping.items():
                if hasattr(self, our_field) and hasattr(pph_settings, pph_field):
                    current_value = pph_settings.get(pph_field)
                    new_value = self.get(our_field)

                    # Handle boolean fields correctly
                    if isinstance(current_value, bool):
                        new_value = cint(new_value) == 1

                    if current_value != new_value:
                        pph_settings.set(pph_field, new_value)
                        needs_update = True

            if needs_update:
                pph_settings.flags.ignore_validate = True
                pph_settings.flags.ignore_permissions = True
                pph_settings.save()
                frappe.msgprint(
                    _("PPh 21 Settings updated from Payroll Indonesia Settings"),
                    indicator="green",
                )

    # Helper methods for retrieving settings data

    def get_ptkp_value(self, status_code: str) -> float:
        """
        Get PTKP value for a specific status code.

        Args:
            status_code: PTKP status code

        Returns:
            float: PTKP amount for the status code
        """
        for row in self.ptkp_table:
            if row.status_pajak == status_code:
                return flt(row.ptkp_amount)

        # Return 0 if not found, but log warning
        logger.warning(f"PTKP status code not found: {status_code}")
        return 0.0

    def get_ter_rate(self, ter_category: str, annual_income: float) -> float:
        """
        Get TER rate for a specific category and income level.

        Args:
            ter_category: TER category (TER A, TER B, TER C)
            annual_income: Annual taxable income

        Returns:
            float: Applicable TER rate (percentage)
        """
        applicable_rate = self.ter_fallback_rate

        # Filter rows by TER category
        category_rows = [row for row in self.ter_rate_table if row.status_pajak == ter_category]

        # Sort by income_from to ensure proper order
        category_rows.sort(key=lambda x: flt(x.income_from))

        # Find applicable rate based on income
        for row in category_rows:
            if annual_income >= flt(row.income_from) and (
                row.is_highest_bracket or annual_income <= flt(row.income_to)
            ):
                applicable_rate = flt(row.rate)
                break

        return applicable_rate

    def get_progressive_tax_rate(self, annual_income: float) -> List[Dict[str, float]]:
        """
        Get progressive tax calculation brackets for annual income.

        Args:
            annual_income: Annual taxable income

        Returns:
            List[Dict[str, float]]: List of applicable tax brackets with calculated amounts
        """
        tax_brackets = []
        remaining_income = annual_income

        # Sort tax brackets by income_from
        sorted_brackets = sorted(self.tax_brackets_table, key=lambda x: flt(x.income_from))

        for i, bracket in enumerate(sorted_brackets):
            income_from = flt(bracket.income_from)
            income_to = flt(bracket.income_to)
            rate = flt(bracket.tax_rate)

            if remaining_income <= 0:
                break

            # For highest bracket (no upper limit)
            if i == len(sorted_brackets) - 1 or income_to == 0:
                taxable_in_bracket = remaining_income
            else:
                taxable_in_bracket = min(remaining_income, income_to - income_from + 1)

            tax_in_bracket = taxable_in_bracket * (rate / 100)

            tax_brackets.append(
                {
                    "income_from": income_from,
                    "income_to": income_to if income_to > 0 else "∞",
                    "rate": rate,
                    "taxable_amount": taxable_in_bracket,
                    "tax_amount": tax_in_bracket,
                }
            )

            remaining_income -= taxable_in_bracket

        return tax_brackets

    def get_ptkp_ter_mapping(self, ptkp_status: str) -> str:
        """
        Get TER category for a PTKP status.

        Args:
            ptkp_status: PTKP status code

        Returns:
            str: Corresponding TER category or default category if not found
        """
        for row in self.ptkp_ter_mapping_table:
            if row.ptkp_status == ptkp_status:
                return row.ter_category

        # Return default if not found
        logger.warning(f"PTKP to TER mapping not found for: {ptkp_status}, using default")
        return self.ter_default_category or "TER A"

    def get_ptkp_values_dict(self) -> Dict[str, float]:
        """
        Return PTKP values as a dictionary.

        Returns:
            Dict[str, float]: Dictionary mapping PTKP status codes to amounts
        """
        ptkp_dict = {}
        for row in self.ptkp_table:
            ptkp_dict[row.status_pajak] = flt(row.ptkp_amount)
        return ptkp_dict

    def get_tax_brackets_list(self) -> List[Dict[str, float]]:
        """
        Return tax brackets as a list of dictionaries.

        Returns:
            List[Dict[str, float]]: List of tax bracket configurations
        """
        brackets = []
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
        types = []
        for row in self.tipe_karyawan:
            types.append(row.tipe_karyawan)
        return types


@frappe.whitelist()
def migrate_json_to_child_table() -> int:
    """Populate :pydata:`gl_account_mappings` from ``defaults.json`` if empty.

    This helper is kept for backward compatibility and simply seeds the child
    table using the values defined in the bundled configuration file.

    Returns:
        int: Number of rows inserted into the child table.
    """

    settings = frappe.get_single("Payroll Indonesia Settings")

    if getattr(settings, "gl_account_mappings", []):
        return 0

    from payroll_indonesia.config import config
    from payroll_indonesia.config.gl_mapper_core import _seed_gl_account_mappings

    defaults = config.get_config()

    before = len(getattr(settings, "gl_account_mappings", []))
    _seed_gl_account_mappings(settings, defaults)
    after = len(getattr(settings, "gl_account_mappings", []))

    if after > before:
        settings.save(ignore_permissions=True)

    return after - before

