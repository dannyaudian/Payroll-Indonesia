# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:08:10 by dannyaudian

"""
Centralized validation functions for Payroll Indonesia.

This module provides validation functions for various document types,
ensuring consistent rule enforcement throughout the application.
"""

import logging
import re
from typing import Any, Dict

import frappe
from frappe import _
from frappe.utils import flt

from payroll_indonesia.config.config import get_live_config

# Configure logger
logger = logging.getLogger(__name__)


def validate_bpjs_settings(doc: Any) -> None:
    """
    Validate BPJS Settings document.

    Args:
        doc: BPJS Settings document
    """
    try:
        logger.info(f"Validating BPJS Settings: {getattr(doc, 'name', 'New')}")

        # Get validation rules from config
        cfg = get_live_config()
        bpjs_config = cfg.get("bpjs", {})
        validation_rules = bpjs_config.get("validation", {})

        # Validate percentage fields
        validate_bpjs_percentages(doc, validation_rules)

        # Validate maximum salary thresholds
        validate_bpjs_max_salary(doc, validation_rules)

        logger.info("BPJS Settings validation completed successfully")
    except Exception as e:
        logger.error(f"BPJS validation error: {str(e)}")
        raise


def validate_bpjs_percentages(doc: Any, validation_rules: Dict[str, Any]) -> None:
    """
    Validate BPJS percentage ranges using rules from configuration.

    Args:
        doc: BPJS Settings document
        validation_rules: Validation rules from configuration
    """
    percentage_limits = validation_rules.get("percentage_limits", {})

    # Fields to validate
    fields = [
        "kesehatan_employee_percent",
        "kesehatan_employer_percent",
        "jht_employee_percent",
        "jht_employer_percent",
        "jp_employee_percent",
        "jp_employer_percent",
        "jkk_percent",
        "jkm_percent",
    ]

    for field in fields:
        if not hasattr(doc, field):
            continue

        value = flt(getattr(doc, field))

        # Get limits from config or use defaults
        field_limits = percentage_limits.get(field, {})
        min_val = flt(field_limits.get("min", 0))
        max_val = flt(field_limits.get("max", 100))

        if value < min_val or value > max_val:
            logger.info(f"BPJS validation: {field}={value} not in range " f"{min_val}-{max_val}")
            frappe.throw(_(f"{field} must be between {min_val}% and {max_val}%"))


def validate_bpjs_max_salary(doc: Any, validation_rules: Dict[str, Any]) -> None:
    """
    Validate BPJS maximum salary thresholds.

    Args:
        doc: BPJS Settings document
        validation_rules: Validation rules from configuration
    """
    salary_limits = validation_rules.get("salary_limits", {})

    # Fields to validate
    fields = ["kesehatan_max_salary", "jp_max_salary"]

    for field in fields:
        if not hasattr(doc, field):
            continue

        value = flt(getattr(doc, field))

        # Get limits from config or use defaults
        field_limits = salary_limits.get(field, {})
        min_val = flt(field_limits.get("min", 0))

        if value < min_val:
            logger.info(f"BPJS validation: {field}={value} below minimum {min_val}")
            frappe.throw(_(f"{field} must be at least {min_val}"))


def validate_payroll_settings(doc: Any) -> None:
    """
    Validate Payroll Indonesia Settings document.

    Args:
        doc: Payroll Indonesia Settings document
    """
    try:
        logger.info(f"Validating Payroll Indonesia Settings: {getattr(doc, 'name', 'New')}")

        # Get validation rules from config
        cfg = get_live_config()
        tax_config = cfg.get("tax", {})
        validation = tax_config.get("validation", {})

        # Validate TER settings
        if hasattr(doc, "tax_calculation_method") and hasattr(doc, "use_ter"):
            if doc.tax_calculation_method == "TER" and not doc.use_ter:
                # Auto-set use_ter if calculation method is TER
                logger.info("Auto-enabling TER since calculation method is TER")
                doc.use_ter = 1

        # Validate biaya jabatan limits
        validate_biaya_jabatan(doc, validation)

        # Validate tax brackets
        validate_tax_brackets(doc)

        # Validate TER configuration
        validate_ter_configuration(doc, tax_config)

        logger.info("Payroll Indonesia Settings validation completed successfully")
    except Exception as e:
        logger.error(f"Payroll settings validation error: {str(e)}")
        raise


def validate_biaya_jabatan(doc: Any, validation: Dict[str, Any]) -> None:
    """
    Validate biaya jabatan percentage and maximum value.

    Args:
        doc: Payroll Indonesia Settings document
        validation: Validation rules from configuration
    """
    if not hasattr(doc, "biaya_jabatan_percent"):
        return

    percent_limits = validation.get("biaya_jabatan_limits", {})
    min_percent = flt(percent_limits.get("min_percent", 0))
    max_percent = flt(percent_limits.get("max_percent", 10))

    value = flt(doc.biaya_jabatan_percent)

    if value < min_percent or value > max_percent:
        logger.info(
            f"Biaya Jabatan percentage {value} outside of allowed range "
            f"({min_percent}%-{max_percent}%)"
        )
        frappe.throw(
            _("Biaya Jabatan percentage must be between {0}% and {1}%").format(
                min_percent, max_percent
            )
        )


def validate_tax_brackets(doc: Any) -> None:
    """
    Validate tax brackets for continuity and logical ordering.

    Args:
        doc: Payroll Indonesia Settings document
    """
    if not hasattr(doc, "tax_brackets_table") or not doc.tax_brackets_table:
        return

    # Sort by income_from
    sorted_brackets = sorted(doc.tax_brackets_table, key=lambda x: flt(x.income_from))

    # Check for gaps or overlaps
    for i in range(len(sorted_brackets) - 1):
        current = sorted_brackets[i]
        next_bracket = sorted_brackets[i + 1]

        if flt(current.income_to) != flt(next_bracket.income_from):
            logger.info(
                f"Tax bracket gap found: {current.income_to} to " f"{next_bracket.income_from}"
            )
            frappe.throw(
                _("Tax brackets must be continuous. Gap found between {0} and {1}").format(
                    current.income_to, next_bracket.income_from
                )
            )


def validate_ter_configuration(doc: Any, tax_config: Dict[str, Any]) -> None:
    """
    Validate TER configuration if TER is enabled.

    Args:
        doc: Payroll Indonesia Settings document
        tax_config: Tax configuration from settings
    """
    if not hasattr(doc, "use_ter") or not doc.use_ter:
        return

    # Check if TER rate table exists and has entries
    if not hasattr(doc, "ter_rate_table") or not doc.ter_rate_table:
        logger.info("TER is enabled but no TER rates defined in ter_rate_table")
        frappe.throw(
            _(
                "TER is enabled but no rates are defined in TER Rate Table. "
                "Please define rates before using this method."
            )
        )

    # Check if all three TER categories (A, B, C) have entries
    ter_categories = {row.status_pajak for row in doc.ter_rate_table}
    expected_categories = {"TER A", "TER B", "TER C"}
    missing_categories = expected_categories - ter_categories

    if missing_categories:
        frappe.throw(
            _("Missing TER rate entries for categories: {0}").format(", ".join(missing_categories))
        )


def validate_employee_golongan(doc: Any) -> None:
    """
    Validate employee golongan against maximum allowed for jabatan.

    Args:
        doc: Employee document
    """
    try:
        logger.info(f"Validating Employee Golongan: {getattr(doc, 'name', 'New')}")

        if not hasattr(doc, "jabatan") or not doc.jabatan:
            return

        if not hasattr(doc, "golongan") or not doc.golongan:
            return

        # Get config settings
        cfg = get_live_config()
        employee_validation = cfg.get("employee_validation", {})
        golongan_validation = employee_validation.get("golongan", {})

        # Check if golongan validation is enabled
        enforce_max_level = golongan_validation.get("enforce_max_level", True)

        # Get maximum golongan for jabatan
        max_golongan = frappe.db.get_value("Jabatan", doc.jabatan, "max_golongan")
        if not max_golongan:
            logger.info(f"Maximum Golongan not set for Jabatan {doc.jabatan}")
            return

        # Get levels for comparison
        max_level = frappe.db.get_value("Golongan", max_golongan, "level")
        current_level = frappe.db.get_value("Golongan", doc.golongan, "level")

        if not max_level or not current_level:
            logger.info("Golongan levels not properly configured")
            return

        if current_level > max_level and enforce_max_level:
            logger.info(
                f"Golongan validation failed: level {current_level} exceeds "
                f"max {max_level} for jabatan '{doc.jabatan}'"
            )
            frappe.throw(
                _(
                    "Employee's Golongan level ({0}) cannot be higher than "
                    "the maximum allowed level ({1}) for the selected Jabatan"
                ).format(current_level, max_level)
            )
        elif current_level > max_level:
            # Notice without throwing error when enforcement is disabled
            logger.info(
                f"Notice: Golongan level {current_level} exceeds max {max_level} "
                f"for jabatan '{doc.jabatan}', but enforcement is disabled"
            )
    except Exception as e:
        logger.error(f"Employee Golongan validation error: {str(e)}")
        raise


def validate_employee_tax_status(doc: Any) -> None:
    """
    Validate employee tax status.

    Args:
        doc: Employee document
    """
    if not hasattr(doc, "status_pajak") or not doc.status_pajak:
        return

    # Get config settings
    cfg = get_live_config()
    employee_validation = cfg.get("employee_validation", {})
    tax_validation = employee_validation.get("tax_status", {})

    # Get valid tax statuses from config
    valid_statuses = tax_validation.get("valid_statuses", [])

    # If not defined in config, use defaults from constants
    if not valid_statuses:
        from payroll_indonesia.constants import VALID_TAX_STATUS

        valid_statuses = VALID_TAX_STATUS

    if doc.status_pajak not in valid_statuses:
        logger.info(
            f"Invalid tax status: {doc.status_pajak}. "
            f"Valid values are: {', '.join(valid_statuses)}"
        )
        frappe.throw(
            _("Invalid tax status: {0}. Valid values are: {1}").format(
                doc.status_pajak, ", ".join(valid_statuses)
            )
        )


def validate_npwp_format(npwp: str) -> bool:
    """
    Validate NPWP format.

    Args:
        npwp: NPWP string to validate

    Returns:
        bool: True if format is valid
    """
    # Get config settings
    cfg = get_live_config()
    employee_validation = cfg.get("employee_validation", {})
    tax_validation = employee_validation.get("tax_id", {})

    # Get NPWP format from config or use default
    npwp_format = tax_validation.get("npwp_format", r"^\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}$")

    return bool(re.match(npwp_format, npwp))


def validate_bpjs_components(company: str = None) -> None:
    """
    Validasi bahwa semua komponen BPJS wajib (Employee dan Employer) sudah ada di sistem.
    Raise error jika ada yang belum dibuat.

    Args:
        company: Optional company name to validate
    """
    required_components = [
        "BPJS Kesehatan Employee",
        "BPJS Kesehatan Employer",
        "BPJS JHT Employee",
        "BPJS JHT Employer",
        "BPJS JP Employee",
        "BPJS JP Employer",
        "BPJS JKK",
        "BPJS JKM",
    ]

    missing = []
    for comp in required_components:
        if not frappe.db.exists("Salary Component", comp):
            missing.append(comp)

    if missing:
        frappe.throw(
            _("Komponen BPJS berikut belum dibuat: {0}").format(", ".join(missing)),
            title="Validasi Komponen BPJS",
        )


def validate_bpjs_account_mapping(company: str = None) -> None:
    """
    Validasi bahwa mapping akun BPJS tersedia untuk perusahaan yang aktif.
    Jika parameter `company` diberikan, maka validasi dilakukan untuk perusahaan tersebut.

    Args:
        company: Optional company name to validate
    """
    companies = [company] if company else frappe.get_all("Company", pluck="name")
    missing = []

    for comp in companies:
        mappings = frappe.get_all("BPJS Account Mapping", filters={"company": comp}, limit=1)
        if not mappings:
            missing.append(comp)

    if missing:
        frappe.throw(
            _("BPJS Account Mapping belum tersedia untuk perusahaan berikut: {0}").format(
                ", ".join(missing)
            ),
            title="Validasi BPJS Mapping",
        )


def validate_ter_rates(ter_category: str) -> None:
    """
    Validate that TER rates are properly defined for a specific category.

    Args:
        ter_category: TER category to validate (TER A, TER B, TER C)
    """
    # Get settings directly from database to avoid circular imports
    if not frappe.db.exists("Payroll Indonesia Settings"):
        frappe.throw(_("Payroll Indonesia Settings not found"))

    # Check if TER rates are defined for this category
    ter_rates = frappe.get_all("PPh 21 TER Table", filters={"status_pajak": ter_category}, limit=1)

    if not ter_rates:
        frappe.throw(
            _("No TER rates defined for category: {0}").format(ter_category),
            title="TER Rate Validation",
        )
