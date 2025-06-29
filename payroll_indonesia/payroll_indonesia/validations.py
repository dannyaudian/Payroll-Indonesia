# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-28 23:52:11 by dannyaudian

import logging
from typing import Dict, Any, List, Optional, Union

import frappe
from frappe import _

from payroll_indonesia.config import get_live_config
from payroll_indonesia.frappe_helpers import safe_execute

# Configure logger
logger = logging.getLogger(__name__)


@frappe.whitelist()
@safe_execute(log_exception=True)
def validate_employee_golongan(jabatan: str, golongan: str) -> None:
    """
    Validate that employee's golongan level does not exceed the maximum allowed for jabatan.

    Args:
        jabatan: The jabatan (position) code
        golongan: The golongan (grade) code

    Raises:
        frappe.ValidationError: If golongan level exceeds maximum allowed level
    """
    if not jabatan:
        frappe.throw(_("Jabatan is required"))

    if not golongan:
        frappe.throw(_("Golongan is required"))

    # Get validation rules from config
    config = get_live_config()
    validation_rules = config.get("validation_rules", {})
    
    # Log the validation attempt
    logger.info(f"Validating golongan '{golongan}' for jabatan '{jabatan}'")

    max_golongan = frappe.db.get_value("Jabatan", jabatan, "max_golongan")
    if not max_golongan:
        logger.warning(f"Maximum Golongan not set for Jabatan {jabatan}")
        frappe.throw(_("Maximum Golongan not set for Jabatan {0}").format(jabatan))

    max_level = frappe.db.get_value("Golongan", max_golongan, "level")
    if not max_level:
        logger.warning(f"Level not set for Golongan {max_golongan}")
        frappe.throw(_("Level not set for Golongan {0}").format(max_golongan))

    current_level = frappe.db.get_value("Golongan", golongan, "level")
    if not current_level:
        logger.warning(f"Level not set for Golongan {golongan}")
        frappe.throw(_("Level not set for Golongan {0}").format(golongan))

    # Check if enforcing max level is enabled in config
    enforce_max_level = validation_rules.get("enforce_golongan_max_level", True)
    
    if current_level > max_level and enforce_max_level:
        logger.warning(
            f"Golongan validation failed: level {current_level} exceeds max {max_level} "
            f"for jabatan '{jabatan}'"
        )
        frappe.throw(
            _(
                "Employee's Golongan level ({0}) cannot be higher than "
                "the maximum allowed level ({1}) for the selected Jabatan"
            ).format(current_level, max_level)
        )
    elif current_level > max_level and not enforce_max_level:
        # Soft notice without throwing error when enforcement is disabled
        logger.info(
            f"Notice: Golongan level {current_level} exceeds max {max_level} "
            f"for jabatan '{jabatan}', but enforcement is disabled"
        )


@frappe.whitelist()
@safe_execute(log_exception=True)
def validate_bpjs_account_mapping(company: str) -> Dict[str, Any]:
    """
    Validate that a BPJS Account Mapping exists for the given company.

    Args:
        company: Company name

    Returns:
        dict: BPJS Account Mapping details if valid

    Raises:
        frappe.ValidationError: If mapping does not exist or is incomplete
    """
    if not company:
        frappe.throw(_("Company is required to validate BPJS Account Mapping"))

    # Get validation rules from config
    config = get_live_config()
    validation_rules = config.get("bpjs_settings", {}).get("validation_rules", {})
    
    # Check if validation is enabled
    enforce_mapping = validation_rules.get("enforce_account_mapping", True)
    
    logger.info(f"Validating BPJS Account Mapping for company '{company}'")

    # Check if mapping exists
    mapping_name = frappe.db.get_value("BPJS Account Mapping", {"company": company}, "name")
    if not mapping_name:
        if enforce_mapping:
            logger.warning(f"BPJS Account Mapping not found for company {company}")
            frappe.throw(
                _("BPJS Account Mapping not found for company {0}. Please create one first.").format(
                    company
                )
            )
        else:
            logger.info(
                f"BPJS Account Mapping not found for company {company}, "
                "but enforcement is disabled"
            )
            return {"status": "warning", "message": "BPJS Account Mapping missing but not enforced"}

    # Get the mapping document
    mapping = frappe.get_doc("BPJS Account Mapping", mapping_name)

    # Get required fields from config
    required_fields = validation_rules.get("required_accounts", [
        "employee_expense_account", 
        "employer_expense_account", 
        "payable_account"
    ])

    missing_fields = []
    for field in required_fields:
        if not mapping.get(field):
            missing_fields.append(frappe.unscrub(field))

    if missing_fields:
        if enforce_mapping:
            logger.warning(
                f"Missing required accounts in BPJS Account Mapping: {', '.join(missing_fields)}"
            )
            frappe.throw(
                _("The following required accounts are missing in BPJS Account Mapping: {0}").format(
                    ", ".join(missing_fields)
                )
            )
        else:
            logger.info(
                f"Missing required accounts in BPJS Account Mapping: {', '.join(missing_fields)}, "
                "but enforcement is disabled"
            )
            return {
                "status": "warning", 
                "message": "Some required accounts are missing but not enforced",
                "missing_fields": missing_fields
            }

    # Return the mapping if all validations pass
    return {
        "status": "success",
        "name": mapping.name,
        "employee_expense_account": mapping.employee_expense_account,
        "employer_expense_account": mapping.employer_expense_account,
        "payable_account": mapping.payable_account,
    }


@frappe.whitelist()
@safe_execute(log_exception=True)
def validate_bpjs_components(
    company: str, 
    salary_structure: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validate that all required BPJS components exist in the salary structure.

    Args:
        company: Company name
        salary_structure: Salary Structure name to validate (optional)

    Returns:
        dict: Validation results

    Raises:
        frappe.ValidationError: If required components are missing
    """
    # First validate BPJS Account Mapping
    mapping = validate_bpjs_account_mapping(company)
    
    # Get validation rules and component list from config
    config = get_live_config()
    validation_rules = config.get("bpjs_settings", {}).get("validation_rules", {})
    components_config = config.get("salary_components", {})
    
    # Check if validation is enabled
    enforce_components = validation_rules.get("enforce_components", True)
    
    # Get required BPJS components from config or use defaults
    required_components = []
    
    # Extract BPJS components from config
    for component in components_config.get("deductions", []):
        if component.get("name", "").startswith("BPJS"):
            required_components.append(component.get("name"))
    
    # Use defaults if not found in config
    if not required_components:
        required_components = [
            "BPJS Kesehatan Employee",
            "BPJS JHT Employee",
            "BPJS JP Employee",
            "BPJS Kesehatan Employer",
            "BPJS JHT Employer",
            "BPJS JP Employer",
            "BPJS JKK",
            "BPJS JKM",
        ]
    
    logger.info(f"Validating BPJS components for company '{company}'")

    # Check if all components exist
    missing_components = []
    for component in required_components:
        if not frappe.db.exists("Salary Component", component):
            missing_components.append(component)

    if missing_components:
        if enforce_components:
            logger.warning(
                f"Missing BPJS components: {', '.join(missing_components)}"
            )
            frappe.throw(
                _("The following BPJS components are missing: {0}").format(
                    ", ".join(missing_components)
                )
            )
        else:
            logger.info(
                f"Missing BPJS components: {', '.join(missing_components)}, "
                "but enforcement is disabled"
            )
            return {
                "status": "warning",
                "message": "Some BPJS components are missing but not enforced",
                "missing_components": missing_components
            }

    # If salary structure is provided, validate components in structure
    if salary_structure:
        return validate_structure_components(
            salary_structure, 
            required_components, 
            enforce_components
        )

    return {"status": "success", "message": _("All BPJS components exist"), "mapping": mapping}


@safe_execute(log_exception=True)
def validate_structure_components(
    salary_structure: str, 
    required_components: List[str],
    enforce_components: bool = True
) -> Dict[str, Any]:
    """
    Validate that all required components exist in the given salary structure.

    Args:
        salary_structure: Salary Structure name
        required_components: List of required component names
        enforce_components: Whether to enforce component validation

    Returns:
        dict: Validation results with missing components if any
    """
    if not frappe.db.exists("Salary Structure", salary_structure):
        logger.warning(f"Salary Structure {salary_structure} does not exist")
        frappe.throw(_("Salary Structure {0} does not exist").format(salary_structure))

    structure = frappe.get_doc("Salary Structure", salary_structure)
    
    logger.info(f"Validating components in salary structure '{salary_structure}'")

    # Get all components in the structure
    structure_components = []
    if hasattr(structure, "earnings"):
        structure_components.extend([d.salary_component for d in structure.earnings])
    if hasattr(structure, "deductions"):
        structure_components.extend([d.salary_component for d in structure.deductions])

    # Find missing components
    missing_in_structure = []
    for component in required_components:
        if component not in structure_components:
            missing_in_structure.append(component)

    if missing_in_structure:
        message = _("Some BPJS components are missing in the salary structure")
        if enforce_components:
            logger.warning(
                f"Missing components in salary structure: {', '.join(missing_in_structure)}"
            )
        else:
            logger.info(
                f"Missing components in salary structure: {', '.join(missing_in_structure)}, "
                "but enforcement is disabled"
            )
            
        return {
            "status": "warning",
            "message": message,
            "missing_components": missing_in_structure,
        }

    logger.info(f"All required components found in salary structure '{salary_structure}'")
    return {
        "status": "success",
        "message": _("All required BPJS components exist in the salary structure"),
    }

# Add this function to existing validations.py

@safe_execute(log_exception=True)
def validate_pph21_settings(doc) -> None:
    """
    Validate PPh 21 Settings document.
    
    Args:
        doc: PPh 21 Settings document
    """
    logger.info("Validating PPh 21 Settings")
    
    # Get validation rules from config
    config = get_live_config()
    tax_limits = config.get("tax", {}).get("limits", {})
    
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
                f"Biaya Jabatan percentage {doc.biaya_jabatan_percent} outside of "
                f"allowed range ({min_biaya_jabatan}%-{max_biaya_jabatan}%)"
            )
            frappe.msgprint(
                _("Biaya Jabatan percentage must be between {0}% and {1}%").format(
                    min_biaya_jabatan, max_biaya_jabatan
                ),
                indicator="orange"
            )
    
    # Validate tax brackets
    if doc.bracket_table and len(doc.bracket_table) > 0:
        # Sort by income_from
        sorted_brackets = sorted(doc.bracket_table, key=lambda x: flt(x.income_from))
        
        # Check for gaps or overlaps
        for i in range(len(sorted_brackets) - 1):
            current = sorted_brackets[i]
            next_bracket = sorted_brackets[i + 1]
            
            if flt(current.income_to) != flt(next_bracket.income_from):
                logger.warning(
                    f"Tax bracket gap found: {current.income_to} to {next_bracket.income_from}"
                )
                frappe.msgprint(
                    _("Warning: Tax brackets should be continuous. Gap found between {0} and {1}")
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

# Add these functions to the existing validations.py file

@safe_execute(log_exception=True)
def validate_bpjs_settings(doc) -> None:
    """
    Validate BPJS Settings document.
    
    Args:
        doc: BPJS Settings document
    """
    logger.info("Validating BPJS Settings")
    
    # Get validation rules from config
    config = get_live_config()
    bpjs_config = config.get("bpjs", {})
    validation_rules = bpjs_config.get("validation_rules", {})
    
    # Validate percentage fields
    _validate_bpjs_percentages(doc, validation_rules)
    
    # Validate maximum salary thresholds
    _validate_bpjs_max_salary(doc, validation_rules)
    
    # Validate account types if specified
    _validate_bpjs_account_types(doc)
    
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
                "error_msg": "BPJS Kesehatan employee percentage must be between 0% and 5%"
            },
            {
                "field": "kesehatan_employer_percent",
                "min": 0,
                "max": 10,
                "error_msg": "BPJS Kesehatan employer percentage must be between 0% and 10%"
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
                "error_msg": "JHT employer percentage must be between 0% and 10%"
            }
        ]
    
    # Validate each field according to rules
    for rule in percentage_rules:
        field = rule.get("field")
        min_val = rule.get("min", 0)
        max_val = rule.get("max", 100)
        error_msg = rule.get("error_msg", f"{field} must be between {min_val}% and {max_val}%")
        
        if hasattr(doc, field):
            value = flt(doc.get(field))
            if value < min_val or value > max_val:
                logger.warning(
                    f"BPJS validation failed: {field}={value} not in range {min_val}-{max_val}"
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
                "error_msg": "BPJS Kesehatan maximum salary must be at least Rp 1.000.000"
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
        error_msg = rule.get("error_msg", f"{field} must be greater than {min_val}")
        
        if hasattr(doc, field):
            value = flt(doc.get(field))
            if value < min_val:
                logger.warning(f"BPJS validation failed: {field}={value} below minimum {min_val}")
                frappe.throw(_(error_msg))


def _validate_bpjs_account_types(doc) -> None:
    """
    Validate that BPJS accounts are of the correct type.
    
    Args:
        doc: BPJS Settings document
    """
    # Get account fields from configuration
    config = get_live_config()
    account_fields = config.get("bpjs_settings", {}).get("account_fields", [])
    
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
                _("Account {0} must be of type 'Payable' or a Liability account").format(account)
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
                defaults["bpjs"][field] = flt(doc.get(field))
        
        # Add app info
        defaults["app_info"] = {
            "version": getattr(doc, "app_version", "1.0.0"),
            "last_updated": str(now_datetime()),
            "updated_by": frappe.session.user
        }
        
        # Write updated defaults to file
        with open(defaults_file, "w") as f:
            json.dump(defaults, f, indent=2)
            
        logger.info(f"BPJS settings synced to defaults.json by {frappe.session.user}")
        
    except Exception as e:
        logger.error(f"Error syncing BPJS settings to defaults.json: {str(e)}")
        frappe.log_error(
            f"Error syncing BPJS settings to defaults.json: {str(e)}",
            "BPJS Settings Sync Error"
        )
