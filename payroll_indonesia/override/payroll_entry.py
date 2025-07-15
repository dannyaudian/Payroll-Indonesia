# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
Payroll Entry - Main override for Indonesia-specific payroll processing
"""

import logging
from typing import Dict, List, Tuple, Any, Optional, Union
from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
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


class CustomPayrollEntry(Document):
    """
    Custom Payroll Entry class for Indonesia-specific payroll functionality.
    """
    
    def validate(self):
        """
        Validate the document before saving.
        """
        self.validate_tax_settings()
    
    def validate_tax_settings(self):
        """
        Validate tax-related settings.
        """
        try:
            # Skip if Indonesia payroll not enabled
            if cint(getattr(self, "calculate_indonesia_tax", 0)) != 1:
                return
            
            # Validate tax method
            tax_method = getattr(self, "tax_method", "Progressive")
            if tax_method not in ["Progressive", "TER"]:
                frappe.throw(_("Invalid tax method. Must be 'Progressive' or 'TER'."))
            
            # If using TER, ensure TER settings are defined
            if tax_method == "TER":
                self._validate_ter_settings()
            
            logger.debug(f"Tax settings validated for payroll entry {getattr(self, 'name', 'unknown')}")
        
        except Exception as e:
            logger.exception(f"Error validating tax settings: {str(e)}")
    
    def _validate_ter_settings(self):
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
    
    def propagate_tax_settings_to_slips(self, slips):
        """
        Propagate tax settings from payroll entry to salary slips.
        
        Args:
            slips: List of salary slip documents
        """
        try:
            if not slips:
                return
            
            # Skip if Indonesia payroll not enabled
            if cint(getattr(self, "calculate_indonesia_tax", 0)) != 1:
                return
            
            # Get settings to propagate
            settings = {
                "calculate_indonesia_tax": 1,
                "tax_method": getattr(self, "tax_method", "Progressive"),
                "is_december_override": cint(getattr(self, "is_december_override", 0))
            }
            
            # Propagate to each slip
            for slip in slips:
                for field, value in settings.items():
                    if hasattr(slip, field):
                        setattr(slip, field, value)
            
            logger.debug(f"Propagated tax settings to {len(slips)} salary slips")
        
        except Exception as e:
            logger.exception(f"Error propagating tax settings: {str(e)}")
    
    def is_december_payroll(self):
        """
        Check if this is a December payroll.
        
        Returns:
            bool: True if December payroll
        """
        try:
            # Check if December override flag is set
            if cint(getattr(self, "is_december_override", 0)) == 1:
                return True
            
            # Check if payroll period includes December
            start_date = getattr(self, "start_date", None)
            end_date = getattr(self, "end_date", None)
            
            if not start_date or not end_date:
                return False
            
            # Convert to date objects
            start_date = getdate(start_date)
            end_date = getdate(end_date)
            
            # Check if December is included
            return (start_date.month == 12 or end_date.month == 12)
        
        except Exception as e:
            logger.exception(f"Error checking December payroll: {str(e)}")
            return False
    
    def set_december_override(self, value=True):
        """
        Set December override flag.
        
        Args:
            value: Value to set (default True)
        """
        try:
            self.is_december_override = 1 if value else 0
            
            # If document is already saved, update in database
            if self.name and not self.is_new():
                frappe.db.set_value("Payroll Entry", self.name, "is_december_override", self.is_december_override)
                frappe.db.commit()
            
            logger.debug(f"Set is_december_override={self.is_december_override} for payroll entry {getattr(self, 'name', 'unknown')}")
        
        except Exception as e:
            logger.exception(f"Error setting December override: {str(e)}")
            
    def use_ter_method(self, value=True):
        """
        Set whether to use TER method for tax calculation.
        
        Args:
            value: Value to set (default True)
        """
        try:
            self.ter_method_enabled = 1 if value else 0
            
            # If document is already saved, update in database
            if self.name and not self.is_new():
                frappe.db.set_value(
                    "Payroll Entry",
                    self.name,
                    "ter_method_enabled",
                    self.ter_method_enabled,
                )
                frappe.db.commit()

            logger.debug(
                f"Set ter_method_enabled={self.ter_method_enabled} for payroll entry {getattr(self, 'name', 'unknown')}"
            )
        
        except Exception as e:
            logger.exception(f"Error setting TER method: {str(e)}")
            
    def update_tax_settings(self, settings: Dict[str, Any]):
        """
        Update tax-related settings in the payroll entry.
        
        Args:
            settings: Dictionary of settings to update
        """
        try:
            # Update fields if they exist
            for field, value in settings.items():
                if hasattr(self, field):
                    setattr(self, field, value)
            
            # If document is already saved, update in database
            if self.name and not self.is_new():
                update_fields = {}
                for field, value in settings.items():
                    if hasattr(self, field):
                        update_fields[field] = value
                
                if update_fields:
                    frappe.db.set_value("Payroll Entry", self.name, update_fields)
                    frappe.db.commit()
            
            logger.debug(f"Updated tax settings for payroll entry {getattr(self, 'name', 'unknown')}")
        
        except Exception as e:
            logger.exception(f"Error updating tax settings: {str(e)}")


class PayrollEntryIndonesia:
    """
    Payroll Entry Indonesia class for extending Payroll Entry functionality.
    This is the main integration point for payroll entry customizations.
    """
    
    def __init__(self, payroll_entry=None):
        """
        Initialize with optional payroll entry document.
        
        Args:
            payroll_entry: Payroll Entry document
        """
        self.doc = payroll_entry
    
    def validate_tax_settings(self):
        """
        Validate tax-related settings.
        """
        try:
            if not self.doc:
                return
            
            # Skip if Indonesia payroll not enabled
            if cint(getattr(self.doc, "calculate_indonesia_tax", 0)) != 1:
                return
            
            # Validate tax method
            tax_method = getattr(self.doc, "tax_method", "Progressive")
            if tax_method not in ["Progressive", "TER"]:
                frappe.throw(_("Invalid tax method. Must be 'Progressive' or 'TER'."))
            
            # If using TER, ensure TER settings are defined
            if tax_method == "TER":
                self._validate_ter_settings()
            
            logger.debug(f"Tax settings validated for payroll entry {getattr(self.doc, 'name', 'unknown')}")
        
        except Exception as e:
            logger.exception(f"Error validating tax settings: {str(e)}")
    
    def _validate_ter_settings(self):
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
    
    def propagate_tax_settings_to_slips(self, slips):
        """
        Propagate tax settings from payroll entry to salary slips.
        
        Args:
            slips: List of salary slip documents
        """
        try:
            if not self.doc or not slips:
                return
            
            # Skip if Indonesia payroll not enabled
            if cint(getattr(self.doc, "calculate_indonesia_tax", 0)) != 1:
                return
            
            # Get settings to propagate
            tax_method = (
                "TER"
                if cint(getattr(self.doc, "ter_method_enabled", 0)) == 1
                else getattr(self.doc, "tax_method", "Progressive")
            )
            settings = {
                "calculate_indonesia_tax": 1,
                "tax_method": tax_method,
                "is_december_override": cint(getattr(self.doc, "is_december_override", 0)),
            }
            
            # Propagate to each slip
            for slip in slips:
                for field, value in settings.items():
                    if hasattr(slip, field):
                        setattr(slip, field, value)
            
            logger.debug(f"Propagated tax settings to {len(slips)} salary slips")
        
        except Exception as e:
            logger.exception(f"Error propagating tax settings: {str(e)}")
    
    def is_december_payroll(self):
        """
        Check if this is a December payroll.
        
        Returns:
            bool: True if December payroll
        """
        try:
            if not self.doc:
                return False
            
            # Check if December override flag is set
            if cint(getattr(self.doc, "is_december_override", 0)) == 1:
                return True
            
            # Check if payroll period includes December
            start_date = getattr(self.doc, "start_date", None)
            end_date = getattr(self.doc, "end_date", None)
            
            if not start_date or not end_date:
                return False
            
            # Convert to date objects
            start_date = getdate(start_date)
            end_date = getdate(end_date)
            
            # Check if December is included
            return (start_date.month == 12 or end_date.month == 12)
        
        except Exception as e:
            logger.exception(f"Error checking December payroll: {str(e)}")
            return False
    
    def set_december_override(self, value=True):
        """
        Set December override flag.
        
        Args:
            value: Value to set (default True)
        """
        try:
            if not self.doc:
                return
            
            self.doc.is_december_override = 1 if value else 0
            
            # If document is already saved, update in database
            if self.doc.name and not self.doc.is_new():
                frappe.db.set_value("Payroll Entry", self.doc.name, "is_december_override", self.doc.is_december_override)
                frappe.db.commit()
            
            logger.debug(f"Set is_december_override={self.doc.is_december_override} for payroll entry {getattr(self.doc, 'name', 'unknown')}")
        
        except Exception as e:
            logger.exception(f"Error setting December override: {str(e)}")