# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
Payroll Entry Functions - Override for Indonesia-specific payroll processing
"""

import logging
from typing import Dict, List, Tuple, Any, Optional, Union
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, add_days, add_months

from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.config.config import get_component_tax_effect, get_live_config
from payroll_indonesia.constants import (
    TAX_DEDUCTION_EFFECT,
    TAX_OBJEK_EFFECT,
    TAX_NON_OBJEK_EFFECT,
    NATURA_OBJEK_EFFECT,
    NATURA_NON_OBJEK_EFFECT,
)


def before_validate(doc, method=None):
    """
    Before validate hook for Payroll Entry.
    
    Args:
        doc: Payroll Entry document
        method: Method name (not used)
    """
    try:
        # Skip if document is already validated
        if hasattr(doc, "flags") and getattr(doc.flags, "skip_indonesia_hooks", False):
            return
        
        # Only process if Indonesia payroll is enabled
        if cint(getattr(doc, "calculate_indonesia_tax", 0)) != 1:
            return
        
        # Handle December override
        _check_december_override(doc)
        
        logger.debug(f"Completed before_validate for payroll entry {getattr(doc, 'name', 'unknown')}")
    
    except Exception as e:
        logger.exception(f"Error in before_validate: {str(e)}")


def validate(doc, method=None):
    """
    Validate hook for Payroll Entry.
    
    Args:
        doc: Payroll Entry document
        method: Method name (not used)
    """
    try:
        # Skip if document is already validated
        if hasattr(doc, "flags") and getattr(doc.flags, "skip_indonesia_hooks", False):
            return
        
        # Only process if Indonesia payroll is enabled
        if cint(getattr(doc, "calculate_indonesia_tax", 0)) != 1:
            return
        
        # Validate tax settings
        _validate_tax_settings(doc)
        
        logger.debug(f"Completed validate for payroll entry {getattr(doc, 'name', 'unknown')}")
    
    except Exception as e:
        logger.exception(f"Error in validate: {str(e)}")


def before_submit(doc, method=None):
    """
    Before submit hook for Payroll Entry.
    
    Args:
        doc: Payroll Entry document
        method: Method name (not used)
    """
    try:
        # Skip if document is already processed
        if hasattr(doc, "flags") and getattr(doc.flags, "skip_indonesia_hooks", False):
            return
        
        # Only process if Indonesia payroll is enabled
        if cint(getattr(doc, "calculate_indonesia_tax", 0)) != 1:
            return
        
        logger.debug(f"Completed before_submit for payroll entry {getattr(doc, 'name', 'unknown')}")
    
    except Exception as e:
        logger.exception(f"Error in before_submit: {str(e)}")


def after_submit(doc, method=None):
    """
    After submit hook for Payroll Entry.
    
    Args:
        doc: Payroll Entry document
        method: Method name (not used)
    """
    try:
        # Skip if document is already processed
        if hasattr(doc, "flags") and getattr(doc.flags, "skip_indonesia_hooks", False):
            return
        
        # Only process if Indonesia payroll is enabled
        if cint(getattr(doc, "calculate_indonesia_tax", 0)) != 1:
            return
        
        logger.debug(f"Completed after_submit for payroll entry {getattr(doc, 'name', 'unknown')}")
    
    except Exception as e:
        logger.exception(f"Error in after_submit: {str(e)}")


def _check_december_override(doc):
    """
    Check and set December override flag if needed.
    
    Args:
        doc: Payroll Entry document
    """
    try:
        # Get start and end dates
        start_date = getattr(doc, "start_date", None)
        end_date = getattr(doc, "end_date", None)
        
        if not start_date or not end_date:
            return
        
        # Convert to date objects
        start_date = getdate(start_date)
        end_date = getdate(end_date)
        
        # Check if December is included
        is_december = (start_date.month == 12 or end_date.month == 12)
        
        # If December is included, check if we should auto-set the override flag
        if is_december:
            # Check if auto-set is enabled in settings
            settings = frappe.get_cached_doc("Payroll Indonesia Settings")
            auto_set_december = cint(getattr(settings, "auto_set_december_override", 0))
            
            if auto_set_december:
                # Only set if not already set
                if not hasattr(doc, "is_december_override") or not doc.is_december_override:
                    doc.is_december_override = 1
                    logger.debug(f"Auto-set December override flag for payroll entry {getattr(doc, 'name', 'unknown')}")
            
            # If manual setting and December, show a message
            elif not getattr(doc, "is_december_override", 0):
                frappe.msgprint(
                    _("This payroll period includes December. Consider enabling the 'December Override' "
                      "flag for year-end tax adjustments."),
                    title=_("December Payroll"),
                    indicator="blue"
                )
    
    except Exception as e:
        logger.exception(f"Error checking December override: {str(e)}")


def _validate_tax_settings(doc):
    """
    Validate tax-related settings.
    
    Args:
        doc: Payroll Entry document
    """
    try:
        # Validate tax method
        tax_method = getattr(doc, "tax_method", "Progressive")
        if tax_method not in ["Progressive", "TER"]:
            frappe.throw(_("Invalid tax method. Must be 'Progressive' or 'TER'."))
        
        # If using TER, ensure TER settings are defined
        if tax_method == "TER":
            _validate_ter_settings()
        
        # Validate that all salary structures have components with defined tax effects
        _validate_component_tax_effects(doc)
    
    except Exception as e:
        logger.exception(f"Error validating tax settings: {str(e)}")


def _validate_ter_settings():
    """
    Validate that TER settings are properly defined.
    """
    try:
        settings = frappe.get_cached_doc("Payroll Indonesia Settings")
        
        # Check if TER rates are defined
        has_ter_rates = False
        
        # Check for ter_rates_json
        if hasattr(settings, "ter_rates_json") and settings.ter_rates_json:
            has_ter_rates = True
        
        # Check for ter_rate_table
        if hasattr(settings, "ter_rate_table") and settings.ter_rate_table:
            has_ter_rates = True
        
        # Check config as fallback
        if not has_ter_rates:
            cfg = get_live_config()
            ter_rates = cfg.get("tax", {}).get("ter_rates", {})
            if ter_rates:
                has_ter_rates = True
        
        if not has_ter_rates:
            frappe.throw(
                _("TER rates are not defined in Payroll Indonesia Settings. "
                  "Please define TER rates before using TER method."),
                title=_("Missing TER Rates")
            )
    
    except Exception as e:
        logger.exception(f"Error validating TER settings: {str(e)}")


def _validate_component_tax_effects(doc):
    """
    Validate that components in salary structures have tax effects defined.
    
    Args:
        doc: Payroll Entry document
    """
    try:
        # Get salary structures used in this payroll entry
        structures = set()
        
        if hasattr(doc, "employees") and doc.employees:
            for employee in doc.employees:
                if employee.salary_structure:
                    structures.add(employee.salary_structure)
        
        if not structures:
            return
        
        # Check components in each structure
        missing_effects = []
        
        for structure_name in structures:
            try:
                structure = frappe.get_doc("Salary Structure", structure_name)
                
                # Check earnings
                if hasattr(structure, "earnings") and structure.earnings:
                    for earning in structure.earnings:
                        component = earning.salary_component
                        tax_effect = get_component_tax_effect(component, "Earning")
                        
                        if not tax_effect:
                            missing_effects.append(f"Earning: {component} (in {structure_name})")
                
                # Check deductions
                if hasattr(structure, "deductions") and structure.deductions:
                    for deduction in structure.deductions:
                        component = deduction.salary_component
                        
                        # Skip PPh 21 component
                        if component == "PPh 21":
                            continue
                        
                        tax_effect = get_component_tax_effect(component, "Deduction")
                        
                        if not tax_effect:
                            missing_effects.append(f"Deduction: {component} (in {structure_name})")
            
            except Exception as e:
                logger.warning(f"Error checking structure {structure_name}: {str(e)}")
        
        # Show warning if components are missing tax effects
        if missing_effects:
            warning_msg = _(
                "The following components are missing tax effect settings. "
                "They will be treated as non-taxable by default:\n{0}"
            ).format("\n".join(missing_effects[:10]))
            
            # If more than 10, show count
            if len(missing_effects) > 10:
                warning_msg += _("\n...and {0} more components").format(len(missing_effects) - 10)
            
            frappe.msgprint(
                warning_msg,
                title=_("Missing Tax Effect Settings"),
                indicator="orange"
            )
    
    except Exception as e:
        logger.exception(f"Error validating component tax effects: {str(e)}")