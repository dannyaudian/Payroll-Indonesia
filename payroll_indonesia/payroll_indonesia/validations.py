# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 00:41:14 by dannyaudian

"""
Centralized validation functions for Payroll Indonesia.

This module provides validation functions for various document types,
ensuring consistent rule enforcement throughout the application.
"""

import logging
from typing import Dict, Any, List, Optional, Union, Tuple

import frappe
from frappe import _

from payroll_indonesia.config import get_live_config
from payroll_indonesia.frappe_helpers import safe_execute

# Configure logger
logger = logging.getLogger(__name__)


@safe_execute(log_exception=True)
def validate_bpjs_settings(doc) -> None:
    """
    Validate BPJS Settings document.
    
    Args:
        doc: BPJS Settings document
    """
    logger.info("Validating BPJS Settings")
    
    # Get validation rules from config
    cfg = get_live_config()
    bpjs_config = cfg.get("bpjs", {})
    validation_rules = bpjs_config.get("validation_rules", {})
    
    # Validate percentage fields
    _validate_bpjs_percentages(doc, validation_rules)
    
    # Validate maximum salary thresholds
    _validate_bpjs_max_salary(doc, validation_rules)
    
    # Validate account types if specified
    _validate_bpjs_account_types(doc, bpjs_config)
    
    logger.info("BPJS Settings validation completed successfully")


def _validate_bpjs_percentages(doc, validation_rules: Dict[str, Any]) -> None:
    """
    Validate BPJS percentage ranges using rules from configuration.
    
    Args:
        doc: BPJS Settings document
        validation_rules: Validation rules from configuration
    """
    percentage_rules = validation_rules.get("percentage_ranges", [])
    
    # If no rules defined, use default critical fields
    if not percentage_rules:
        percentage_rules = [
            {
                "field": "kesehatan_employee_percent",
                "min": 0,
                "max": 5,
                "error_msg": "BPJS Kesehatan employee percentage must be "
                             "between 0% and 5%"
            },
            {
                "field": "kesehatan_employer_percent",
                "min": 0,
                "max": 10,
                "error_msg": "BPJS Kesehatan employer percentage must be "
                             "between 0% and 10%"
            },
            {
                "field": "jht_employee_percent",
                "min": 0,
                "max": 5,
                "error_msg": "JHT employee percentage must be between 0% and 5%"
            },
            {
                "field": "jht_employer_percent",
                "min": 0,
                "max": 10,
                "error_msg": "JHT employer percentage must be "
                             "between 0% and 10%"
            },
            {
                "field": "jp_employee_percent",
                "min": 0,
                "max": 5,
                "error_msg": "JP employee percentage must be between 0% and 5%"
            },
            {
                "field": "jp_employer_percent",
                "min": 0,
                "max": 5,
                "error_msg": "JP employer percentage must be between 0% and 5%"
            },
            {
                "field": "jkk_percent",
                "min": 0,
                "max": 5,
                "error_msg": "JKK percentage must be between 0% and 5%"
            },
            {
                "field": "jkm_percent",
                "min": 0,
                "max": 5,
                "error_msg": "JKM percentage must be between 0% and 5%"
            }
        ]
    
    # Validate each field according to rules
    for rule in percentage_rules:
        field = rule.get("field")
        min_val = rule.get("min", 0)
        max_val = rule.get("max", 100)
        error_msg = rule.get(
            "error_msg", 
            f"{field} must be between {min_val}% and {max_val}%"
        )
        
        if hasattr(doc, field):
            value = frappe.utils.flt(doc.get(field))
            if value < min_val or value > max_val:
                logger.warning(
                    f"BPJS validation failed: {field}={value} not in range "
                    f"{min_val}-{max_val}"
                )
                frappe.throw(_(error_msg))


def _validate_bpjs_max_salary(doc, validation_rules: Dict[str, Any]) -> None:
    """
    Validate BPJS maximum salary thresholds.
    
    Args:
        doc: BPJS Settings document
        validation_rules: Validation rules from configuration
    """
    salary_rules = validation_rules.get("salary_thresholds", [])
    
    # If no rules defined, use default critical fields
    if not salary_rules:
        salary_rules = [
            {
                "field": "kesehatan_max_salary",
                "min": 1000000,
                "error_msg": "BPJS Kesehatan maximum salary must be at least "
                             "Rp 1.000.000"
            },
            {
                "field": "jp_max_salary",
                "min": 1000000,
                "error_msg": "JP maximum salary must be at least Rp 1.000.000"
            }
        ]
    
    # Validate each field according to rules
    for rule in salary_rules:
        field = rule.get("field")
        min_val = rule.get("min", 0)
        error_msg = rule.get(
            "error_msg",
            f"{field} must be greater than {min_val}"
        )
        
        if hasattr(doc, field):
            value = frappe.utils.flt(doc.get(field))
            if value < min_val:
                logger.warning(
                    f"BPJS validation failed: {field}={value} below minimum "
                    f"{min_val}"
                )
                frappe.throw(_(error_msg))


def _validate_bpjs_account_types(doc, bpjs_config: Dict[str, Any]) -> None:
    """
    Validate that BPJS accounts are of the correct type.
    
    Args:
        doc: BPJS Settings document
        bpjs_config: BPJS configuration from settings
    """
    # Get account fields from configuration
    account_fields = bpjs_config.get("account_fields", [])
    
    # If no fields defined, use defaults
    if not account_fields:
        account_fields = [
            "kesehatan_account",
            "jht_account",
            "jp_account",
            "jkk_account",
            "jkm_account",
        ]
    
    # Validate each account
    for field in account_fields:
        if not hasattr(doc, field) or not doc.get(field):
            continue
            
        account = doc.get(field)
        account_data = frappe.db.get_value(
            "Account",
            account,
            ["account_type", "root_type", "company", "is_group"],
            as_dict=1
        )
        
        if not account_data:
            logger.warning(f"Account {account} does not exist")
            frappe.throw(_("Account {0} does not exist").format(account))
            
        if account_data.root_type != "Liability" or (
            account_data.account_type not in ["Payable", "Liability"]
        ):
            logger.warning(
                f"Account {account} has wrong type: root={account_data.root_type}, "
                f"type={account_data.account_type}"
            )
            frappe.throw(
                _("Account {0} must be of type 'Payable' or a Liability account")
                .format(account)
            )


@safe_execute(log_exception=True)
def validate_pph21_settings(doc) -> None:
    """
    Validate PPh 21 Settings document.
    
    Args:
        doc: PPh 21 Settings document
    """
    logger.info("Validating PPh 21 Settings")
    
    # Get validation rules from config
    cfg = get_live_config()
    tax_config = cfg.get("tax", {})
    tax_limits = tax_config.get("limits", {})
    
    # Validate TER settings
    if doc.calculation_method == "TER" and not doc.use_ter:
        # Auto-set use_ter if calculation method is TER but use_ter isn't checked
        logger.info("Auto-enabling TER since calculation method is TER")
        doc.use_ter = 1
    
    # Validate biaya jabatan limits
    min_biaya_jabatan = tax_limits.get("min_biaya_jabatan_percent", 0)
    max_biaya_jabatan = tax_limits.get("max_biaya_jabatan_percent", 10)
    
    if hasattr(doc, "biaya_jabatan_percent"):
        if (doc.biaya_jabatan_percent < min_biaya_jabatan or 
                doc.biaya_jabatan_percent > max_biaya_jabatan):
            logger.warning(
                f"Biaya Jabatan percentage {doc.biaya_jabatan_percent} outside "
                f"of allowed range ({min_biaya_jabatan}%-{max_biaya_jabatan}%)"
            )
            frappe.msgprint(
                _("Biaya Jabatan percentage must be between {0}% and {1}%")
                .format(min_biaya_jabatan, max_biaya_jabatan),
                indicator="orange"
            )
    
    # Validate tax brackets
    if doc.bracket_table and len(doc.bracket_table) > 0:
        # Sort by income_from
        sorted_brackets = sorted(
            doc.bracket_table, 
            key=lambda x: frappe.utils.flt(x.income_from)
        )
        
        # Check for gaps or overlaps
        for i in range(len(sorted_brackets) - 1):
            current = sorted_brackets[i]
            next_bracket = sorted_brackets[i + 1]
            
            if frappe.utils.flt(current.income_to) != frappe.utils.flt(
                    next_bracket.income_from):
                logger.warning(
                    f"Tax bracket gap found: {current.income_to} to "
                    f"{next_bracket.income_from}"
                )
                frappe.msgprint(
                    _("Warning: Tax brackets should be continuous. "
                      "Gap found between {0} and {1}")
                    .format(current.income_to, next_bracket.income_from),
                    indicator="orange"
                )
    
    # Validate TER configuration if TER is enabled
    if doc.use_ter:
        # Check if TER table exists and has entries
        ter_count = frappe.db.count("PPh 21 TER Table")
        if ter_count == 0:
            logger.warning("TER is enabled but no TER rates defined")
            frappe.msgprint(
                _("TER is enabled but no rates are defined in PPh 21 TER Table. "
                  "Please define rates before using this method."),
                indicator="orange"
            )


@safe_execute(log_exception=True)
def validate_employee(doc) -> None:
    """
    Validate Employee document.
    
    Args:
        doc: Employee document
    """
    logger.info(f"Validating Employee: {doc.name}")
    
    # Get validation rules from config
    cfg = get_live_config()
    employee_validation = cfg.get("employee_validation", {})
    
    # Validate tax status
    _validate_employee_tax_status(doc, employee_validation)
    
    # Validate golongan if enabled
    if employee_validation.get("validate_golongan", True):
        _validate_employee_golongan(doc, employee_validation)
    
    # Validate NPWP/KTP if enabled
    if employee_validation.get("validate_tax_id", True):
        _validate_employee_tax_id(doc, employee_validation)


def _validate_employee_tax_status(
    doc, 
    validation_rules: Dict[str, Any]
) -> None:
    """
    Validate employee tax status.
    
    Args:
        doc: Employee document
        validation_rules: Validation rules from configuration
    """
    if not hasattr(doc, "status_pajak"):
        return
        
    # Get valid tax statuses from config
    valid_statuses = validation_rules.get("valid_tax_statuses", [])
    
    # If not defined in config, use defaults
    if not valid_statuses:
        valid_statuses = [
            "TK0", "TK1", "TK2", "TK3", 
            "K0", "K1", "K2", "K3", 
            "HB0", "HB1", "HB2", "HB3"
        ]
    
    if doc.status_pajak and doc.status_pajak not in valid_statuses:
        logger.warning(
            f"Invalid tax status: {doc.status_pajak}. "
            f"Valid values are: {', '.join(valid_statuses)}"
        )
        frappe.throw(
            _("Invalid tax status: {0}. Valid values are: {1}")
            .format(doc.status_pajak, ", ".join(valid_statuses))
        )


def _validate_employee_golongan(
    doc, 
    validation_rules: Dict[str, Any]
) -> None:
    """
    Validate employee golongan against maximum allowed for jabatan.
    
    Args:
        doc: Employee document
        validation_rules: Validation rules from configuration
    """
    if not hasattr(doc, "jabatan") or not doc.jabatan:
        return
        
    if not hasattr(doc, "golongan") or not doc.golongan:
        return
    
    # Check if golongan validation is enabled
    enforce_max_level = validation_rules.get("enforce_golongan_max_level", True)
    
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
        logger.warning(
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
        # Soft notice without throwing error when enforcement is disabled
        logger.info(
            f"Notice: Golongan level {current_level} exceeds max {max_level} "
            f"for jabatan '{doc.jabatan}', but enforcement is disabled"
        )
        frappe.msgprint(
            _(
                "Notice: Employee's Golongan level ({0}) is higher than "
                "the recommended level ({1}) for the selected Jabatan"
            ).format(current_level, max_level),
            indicator="orange"
        )


def _validate_employee_tax_id(
    doc, 
    validation_rules: Dict[str, Any]
) -> None:
    """
    Validate employee tax IDs (NPWP/KTP).
    
    Args:
        doc: Employee document
        validation_rules: Validation rules from configuration
    """
    # Check if NPWP is required
    npwp_required = validation_rules.get("npwp_required", False)
    
    if npwp_required and not (hasattr(doc, "npwp") and doc.npwp):
        logger.warning(f"NPWP is required but not provided for {doc.name}")
        frappe.throw(_("NPWP is required for all employees"))
    
    # Validate NPWP format if provided
    if hasattr(doc, "npwp") and doc.npwp:
        npwp_format = validation_rules.get("npwp_format", r"^\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}$")
        import re
        if not re.match(npwp_format, doc.npwp):
            logger.warning(f"Invalid NPWP format: {doc.npwp}")
            frappe.msgprint(
                _("Invalid NPWP format. Expected format: XX.XXX.XXX.X-XXX.XXX"),
                indicator="orange"
            )


@safe_execute(log_exception=True)
def validate_salary_slip(doc) -> None:
    """
    Validate Salary Slip document.
    
    Args:
        doc: Salary Slip document
    """
    logger.info(f"Validating Salary Slip: {doc.name}")
    
    # Get validation rules from config
    cfg = get_live_config()
    salary_validation = cfg.get("salary_validation", {})
    
    # Validate salary slip dates
    _validate_salary_slip_dates(doc, salary_validation)
    
    # Validate salary components
    _validate_salary_components(doc, salary_validation)
    
    # Validate tax calculation
    _validate_tax_calculation(doc, cfg.get("tax", {}))


def _validate_salary_slip_dates(
    doc, 
    validation_rules: Dict[str, Any]
) -> None:
    """
    Validate salary slip dates.
    
    Args:
        doc: Salary Slip document
        validation_rules: Validation rules from configuration
    """
    # Check start_date and end_date relationship
    if doc.start_date and doc.end_date and doc.start_date > doc.end_date:
        logger.warning(
            f"Start date {doc.start_date} is after end date {doc.end_date}"
        )
        frappe.throw(_("Start Date cannot be after End Date"))
    
    # Validate posting date
    max_backdated_days = validation_rules.get("max_backdated_days", 0)
    max_future_days = validation_rules.get("max_future_days", 0)
    
    if doc.posting_date:
        today = frappe.utils.today()
        
        # Check backdated posting
        days_before = frappe.utils.date_diff(today, doc.posting_date)
        if days_before > max_backdated_days and max_backdated_days > 0:
            logger.warning(
                f"Posting date {doc.posting_date} is {days_before} days in the "
                f"past, exceeding limit of {max_backdated_days} days"
            )
            frappe.msgprint(
                _("Posting Date is {0} days in the past. Maximum allowed is {1}.")
                .format(days_before, max_backdated_days),
                indicator="orange"
            )
        
        # Check future posting
        days_after = frappe.utils.date_diff(doc.posting_date, today)
        if days_after > max_future_days and max_future_days > 0:
            logger.warning(
                f"Posting date {doc.posting_date} is {days_after} days in the "
                f"future, exceeding limit of {max_future_days} days"
            )
            frappe.msgprint(
                _("Posting Date is {0} days in the future. Maximum allowed is {1}.")
                .format(days_after, max_future_days),
                indicator="orange"
            )


def _validate_salary_components(
    doc, 
    validation_rules: Dict[str, Any]
) -> None:
    """
    Validate salary components in salary slip.
    
    Args:
        doc: Salary Slip document
        validation_rules: Validation rules from configuration
    """
    # Check required components
    required_components = validation_rules.get("required_components", [])
    
    if required_components:
        # Get all components in the slip
        slip_components = []
        if hasattr(doc, "earnings"):
            slip_components.extend([d.salary_component for d in doc.earnings])
        if hasattr(doc, "deductions"):
            slip_components.extend([d.salary_component for d in doc.deductions])
        
        # Check for missing required components
        missing_components = []
        for component in required_components:
            if component not in slip_components:
                missing_components.append(component)
        
        if missing_components:
            logger.warning(
                f"Missing required components in salary slip: "
                f"{', '.join(missing_components)}"
            )
            frappe.msgprint(
                _("Missing required components: {0}")
                .format(", ".join(missing_components)),
                indicator="orange"
            )


def _validate_tax_calculation(doc, tax_config: Dict[str, Any]) -> None:
    """
    Validate tax calculation in salary slip.
    
    Args:
        doc: Salary Slip document
        tax_config: Tax configuration from settings
    """
    # Check TER configuration
    if hasattr(doc, "is_using_ter") and doc.is_using_ter:
        # Check if TER rate is set
        if not hasattr(doc, "ter_rate") or not doc.ter_rate:
            logger.warning("TER is enabled but TER rate is not set")
            frappe.msgprint(
                _("TER calculation is enabled but no TER rate is set"),
                indicator="orange"
            )
        
        # Validate December override
        december_month = tax_config.get("december_month", 12)
        if doc.month == december_month and doc.is_using_ter:
            logger.warning(
                f"TER should not be used for month {december_month} (December)"
            )
            frappe.msgprint(
                _("TER calculation should not be used for December payroll. "
                  "Progressive method is recommended."),
                indicator="orange"
            )


@safe_execute(log_exception=True)
def sync_bpjs_to_defaults(doc) -> None:
    """
    Sync BPJS settings to defaults.json configuration.
    
    Args:
        doc: BPJS Settings document
    """
    try:
        import os
        import json
        from pathlib import Path
        
        # Get app path
        app_path = frappe.get_app_path("payroll_indonesia")
        config_path = Path(app_path) / "config"
        defaults_file = config_path / "defaults.json"
        
        # Ensure config directory exists
        if not config_path.exists():
            os.makedirs(config_path)
        
        # Read existing defaults if file exists
        if defaults_file.exists():
            with open(defaults_file, "r") as f:
                defaults = json.load(f)
        else:
            defaults = {}
        
        # Ensure bpjs section exists
        if "bpjs" not in defaults:
            defaults["bpjs"] = {}
        
        # Update BPJS settings
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
        
        for field in bpjs_fields:
            if hasattr(doc, field):
                defaults["bpjs"][field] = frappe.utils.flt(doc.get(field))
        
        # Add app info
        defaults["app_info"] = {
            "version": getattr(doc, "app_version", "1.0.0"),
            "last_updated": str(frappe.utils.now_datetime()),
            "updated_by": frappe.session.user
        }
        
        # Write updated defaults to file
        with open(defaults_file, "w") as f:
            json.dump(defaults, f, indent=2)
            
        logger.info(
            f"BPJS settings synced to defaults.json by {frappe.session.user}"
        )
        
    except Exception as e:
        logger.error(f"Error syncing BPJS settings to defaults.json: {str(e)}")
        frappe.log_error(
            f"Error syncing BPJS settings to defaults.json: {str(e)}",
            "BPJS Settings Sync Error"
        )
