# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
Centralized validation functions for Payroll Indonesia.

This module provides validation functions for various document types,
ensuring consistent rule enforcement throughout the application.
"""

import re
from typing import Any, Dict, Union, List, Optional

import frappe
from frappe import _
from frappe.utils import flt, cint

from payroll_indonesia.config.config import get_live_config, get_component_tax_effect
from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.constants import (
    TAX_DEDUCTION_EFFECT,
    TAX_OBJEK_EFFECT,
    TAX_NON_OBJEK_EFFECT,
    NATURA_OBJEK_EFFECT,
    NATURA_NON_OBJEK_EFFECT,
    VALID_TAX_EFFECTS,
)

__all__ = [
    # Employee validations
    "validate_employee_fields",
    "validate_employee_golongan",
    # Tax validations
    "validate_tax_status",
    "validate_component_tax_effects",
    "validate_salary_structure_tax_effects",
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


def validate_component_tax_effects(components: List[Dict[str, Any]], 
                                  component_type: str, 
                                  throw_error: bool = True) -> List[str]:
    """
    Validate that components have tax effects defined.
    
    Args:
        components: List of component dictionaries with 'salary_component' key
        component_type: Type of component ('Earning' or 'Deduction')
        throw_error: Whether to throw error on validation failure
        
    Returns:
        List[str]: List of components without tax effect
    """
    missing_effects = []
    
    for component_dict in components:
        component_name = component_dict.get('salary_component')
        if not component_name:
            continue
            
        # Skip PPh 21 component for deductions
        if component_type == "Deduction" and component_name == "PPh 21":
            continue
            
        tax_effect = get_component_tax_effect(component_name, component_type)
        
        if not tax_effect:
            missing_effects.append(component_name)
    
    if missing_effects and throw_error:
        components_list = ", ".join(missing_effects[:10])
        if len(missing_effects) > 10:
            components_list += f" and {len(missing_effects) - 10} more"
        
        frappe.throw(
            _("The following {0} components do not have tax effects defined: {1}").format(
                component_type, components_list
            ),
            title=_("Missing Tax Effect Settings")
        )
    
    return missing_effects


def validate_salary_structure_tax_effects(doc: Any) -> None:
    """
    Validate that all components in a salary structure have tax effects defined.
    
    Args:
        doc: Salary Structure document
    """
    try:
        # Skip validation if not configured to require tax effects
        cfg = get_live_config()
        validation_cfg = cfg.get("validation", {})
        require_tax_effects = cint(validation_cfg.get("require_tax_effects", 0))
        
        if not require_tax_effects:
            return
        
        # Collect components
        earnings = getattr(doc, "earnings", [])
        deductions = getattr(doc, "deductions", [])
        
        # Convert to list of dicts if not already
        earnings_list = [e.as_dict() if hasattr(e, "as_dict") else e for e in earnings]
        deductions_list = [d.as_dict() if hasattr(d, "as_dict") else d for d in deductions]
        
        # Validate tax effects
        missing_earnings = validate_component_tax_effects(earnings_list, "Earning", False)
        missing_deductions = validate_component_tax_effects(deductions_list, "Deduction", False)
        
        # Report combined results
        missing_all = missing_earnings + missing_deductions
        if missing_all:
            components_list = ", ".join(missing_all[:10])
            if len(missing_all) > 10:
                components_list += f" and {len(missing_all) - 10} more"
            
            frappe.msgprint(
                _("The following components do not have tax effects defined: {0}").format(
                    components_list
                ),
                title=_("Missing Tax Effect Settings"),
                indicator="orange"
            )
    except Exception as e:
        logger.error(f"Error validating salary structure tax effects: {e}")


def validate_tax_effect_type(tax_effect: str) -> bool:
    """
    Validate that a tax effect type is valid.
    
    Args:
        tax_effect: Tax effect type to validate
        
    Returns:
        bool: True if valid, False if not
    """
    return tax_effect in VALID_TAX_EFFECTS


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
        
    # Also validate that BPJS components have the correct tax effect (Tax Deduction)
    for comp in required_components:
        if frappe.db.exists("Salary Component", comp):
            # Determine component type based on name
            component_type = "Earning" if "Employer" in comp else "Deduction"
            
            # Get tax effect
            tax_effect = get_component_tax_effect(comp, component_type)
            
            # Check if it's a tax deduction
            if tax_effect != TAX_DEDUCTION_EFFECT:
                # Log warning and update tax effect
                logger.warning(
                    f"BPJS component {comp} has incorrect tax effect: {tax_effect}. "
                    f"Should be {TAX_DEDUCTION_EFFECT}."
                )
                
                # Show warning message
                frappe.msgprint(
                    _("BPJS component {0} should have tax effect '{1}' but has '{2}'. "
                      "Consider updating its tax effect setting.").format(
                        comp, TAX_DEDUCTION_EFFECT, tax_effect or _("Not set")
                    ),
                    title=_("Incorrect Tax Effect"),
                    indicator="orange"
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


def validate_components_tax_effects_consistency(doc: Any) -> None:
    """
    Validate consistency of tax effects for components across multiple documents.
    
    Checks that components used in multiple salary structures have consistent
    tax effect settings.
    
    Args:
        doc: Salary Component document or Salary Structure document
    """
    try:
        # If document is a Salary Component, check its usage across structures
        if getattr(doc, "doctype", "") == "Salary Component":
            component_name = doc.name
            component_type = doc.type
            
            # Get all structures using this component
            structures = frappe.get_all(
                "Salary Detail",
                filters={
                    "salary_component": component_name,
                    "parenttype": "Salary Structure"
                },
                fields=["parent"],
                distinct=True
            )
            
            if len(structures) <= 1:
                # No consistency issues if used in 0 or 1 structure
                return
            
            # Get tax effect for this component
            tax_effect = get_component_tax_effect(component_name, component_type)
            
            # Log for awareness
            logger.info(
                f"Component {component_name} is used in {len(structures)} salary structures "
                f"with tax effect '{tax_effect or 'Not set'}'"
            )
            
            # Only show warning if no tax effect is set
            if not tax_effect:
                frappe.msgprint(
                    _("Component {0} is used in {1} salary structures but has no tax effect defined. "
                      "Consider setting a tax effect for consistent tax calculations.").format(
                        component_name, len(structures)
                    ),
                    title=_("Missing Tax Effect"),
                    indicator="orange"
                )
        
        # If document is a Salary Structure, validate all its components
        elif getattr(doc, "doctype", "") == "Salary Structure":
            structure_name = doc.name
            
            # Get all components used in this structure
            components = {}
            
            # Process earnings
            for earning in getattr(doc, "earnings", []):
                component_name = getattr(earning, "salary_component", "")
                if component_name:
                    components[component_name] = "Earning"
            
            # Process deductions
            for deduction in getattr(doc, "deductions", []):
                component_name = getattr(deduction, "salary_component", "")
                if component_name:
                    components[component_name] = "Deduction"
            
            # Check tax effects for all components
            missing_effects = []
            for component_name, component_type in components.items():
                tax_effect = get_component_tax_effect(component_name, component_type)
                if not tax_effect:
                    missing_effects.append(f"{component_name} ({component_type})")
            
            # Show warning if components are missing tax effects
            if missing_effects:
                components_list = ", ".join(missing_effects[:10])
                if len(missing_effects) > 10:
                    components_list += f" and {len(missing_effects) - 10} more"
                
                frappe.msgprint(
                    _("The following components in structure {0} have no tax effect defined: {1}").format(
                        structure_name, components_list
                    ),
                    title=_("Missing Tax Effects"),
                    indicator="orange"
                )
    except Exception as e:
        logger.error(f"Error validating component tax effect consistency: {e}")
