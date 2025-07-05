# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:08:10 by dannyaudian

"""
Centralized validation functions for Payroll Indonesia.

This module provides validation functions for various document types,
ensuring consistent rule enforcement throughout the application.
"""

import re
from typing import Any, Dict, Union

import frappe
from frappe import _
from frappe.utils import flt

from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.frappe_helpers import logger

__all__ = [
    # Employee validations
    "validate_employee_fields",
    "validate_employee_golongan",
    
    # Tax validations
    "validate_tax_status",
    
    # BPJS validations
    "validate_bpjs_components",
    "validate_bpjs_account_mapping",
    
    # TER validations
    "validate_ter_rates",
]

# =====================
# Employee Validations
# =====================

def validate_employee_fields(employee: Union[str, Any]) -> None:
    """
    Validate essential fields for an Employee.
    
    Checks for correct golongan, tax status, and NPWP format.

    Args:
        employee: Employee document or ID
    """
    try:
        doc = frappe.get_doc("Employee", employee) if isinstance(employee, str) else employee

        validate_employee_golongan(doc)
        validate_employee_tax_status(doc)

        if getattr(doc, "npwp", None):
            if not validate_npwp_format(doc.npwp):
                frappe.throw(
                    _("Invalid NPWP format for employee {0}").format(doc.name),
                    title="NPWP Validation",
                )
    except Exception as e:
        logger.error(f"Employee field validation error: {e}")
        raise


def validate_employee_golongan(doc: Any) -> None:
    """
    Validate employee golongan against maximum allowed for jabatan.
    
    Ensures the employee's golongan level does not exceed what is permitted
    for their job position (jabatan).

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
    Validate employee tax status against permitted values.
    
    Checks if the employee's tax status (status_pajak) is in the list of 
    valid statuses defined in configuration or constants.

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
    Validate NPWP format using regex pattern from configuration.
    
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


# =====================
# Tax Validations
# =====================

def validate_tax_status(status: str) -> None:
    """
    Validate a tax status string against allowed values.
    
    Creates a dummy object with the status_pajak attribute and passes it
    to the employee tax status validator.
    
    Args:
        status: Tax status string to validate
    """
    dummy = type("Obj", (), {"status_pajak": status})
    validate_employee_tax_status(dummy)


# =====================
# BPJS Validations
# =====================

def validate_bpjs_components(company: str = None) -> None:
    """
    Validate that all required BPJS components exist in the system.
    
    Checks that all required BPJS salary components for both employee and
    employer contributions are properly created in the system.
    
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
    Validate that BPJS account mappings exist for active companies.
    
    Checks that BPJS Account Mapping documents exist for the specified company
    or all companies if none is specified.
    
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


# =====================
# TER Validations
# =====================

def validate_ter_rates(ter_category: str) -> None:
    """
    Validate that TER rates are properly defined for a specific category.
    
    Checks that PPh 21 TER Table contains entries for the specified TER category.
    
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