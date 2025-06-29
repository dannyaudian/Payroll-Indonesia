# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 00:04:51 by dannyaudian

"""PPh 21 Settings DocType controller with centralized validation."""

import json
import logging
from typing import Dict, Any, List, Optional

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint, now_datetime

from payroll_indonesia.config import get_live_config
from payroll_indonesia.frappe_helpers import safe_execute
import payroll_indonesia.payroll_indonesia.validations as validations  # Corrected import path

# Configure logger
logger = logging.getLogger("payroll_settings")


class PPh21Settings(Document):
    """Controller for PPh 21 Settings DocType with centralized validation."""
    
    def __init__(self, *args, **kwargs):
        super(PPh21Settings, self).__init__(*args, **kwargs)
        # Flag to prevent recursion during updates
        self._updating_from_config = False
        
    def validate(self):
        """Validate settings using centralized validation module."""
        try:
            # Delegate validation to central validations module
            validations.validate_pph21_settings(self)
            
            # Ensure required tables exist
            self._ensure_tax_brackets()
            self._ensure_ptkp_values()
            
            # Sync with parent settings when changed directly
            if not self._updating_from_config:
                self._sync_to_payroll_settings()
                
        except Exception as e:
            logger.error(f"Error validating PPh 21 Settings: {str(e)}")
            frappe.log_error(f"Error in PPh 21 Settings validation: {str(e)}")
    
    def on_update(self):
        """Update settings when document is updated."""
        # Avoid recursion if updating from config
        if self._updating_from_config or getattr(self.flags, "ignore_on_update", False):
            return
            
        try:
            # Set flag to prevent recursion
            self._updating_from_config = True
            # Sync from parent settings
            self._sync_from_payroll_settings()
        finally:
            # Always reset flag
            self._updating_from_config = False
    
    @safe_execute(log_exception=True)
    def _ensure_tax_brackets(self):
        """Ensure tax brackets table has values."""
        if not self.bracket_table or len(self.bracket_table) == 0:
            # Get tax brackets from configuration
            config = get_live_config()
            brackets = config.get("tax_brackets", [])
            
            if brackets:
                # Clear any existing entries
                self.set("bracket_table", [])
                
                # Add brackets from config
                for bracket in brackets:
                    self.append(
                        "bracket_table",
                        {
                            "income_from": flt(bracket.get("income_from", 0)),
                            "income_to": flt(bracket.get("income_to", 0)),
                            "tax_rate": flt(bracket.get("tax_rate", 0)),
                        },
                    )
                
                logger.info("Loaded tax brackets from configuration")
    
    @safe_execute(log_exception=True)
    def _ensure_ptkp_values(self):
        """Ensure PTKP values table has values."""
        if not self.ptkp_table or len(self.ptkp_table) == 0:
            # Get PTKP values from configuration
            config = get_live_config()
            ptkp_values = config.get("ptkp", {})
            
            if ptkp_values:
                # Clear any existing entries
                self.set("ptkp_table", [])
                
                # Add PTKP values from config
                for status, amount in ptkp_values.items():
                    # Skip non-status keys
                    if status in ["pribadi", "kawin", "anak"]:
                        continue
                        
                    # Create appropriate description
                    description = self._get_ptkp_description(status)
                    
                    self.append(
                        "ptkp_table",
                        {
                            "status_pajak": status,
                            "description": description,
                            "ptkp_amount": flt(amount),
                        },
                    )
                
                logger.info("Loaded PTKP values from configuration")
    
    def _get_ptkp_description(self, status):
        """Get human-readable description for PTKP status."""
        # Parse status code
        if status.startswith("TK"):
            prefix = "Tidak Kawin"
            dependents = status[2:]
        elif status.startswith("K"):
            prefix = "Kawin"
            dependents = status[1:]
        elif status.startswith("HB"):
            prefix = "Kawin, Penghasilan Istri-Suami Digabung"
            dependents = status[2:]
        else:
            return status

        # Parse dependents
        try:
            num_dependents = int(dependents)
            if num_dependents == 0:
                return f"{prefix}, Tanpa Tanggungan"
            else:
                return f"{prefix}, {num_dependents} Tanggungan"
        except ValueError:
            return status
    
    @safe_execute(log_exception=True)
    def _sync_from_payroll_settings(self):
        """Update settings from Payroll Indonesia Settings."""
        # Get centralized settings
        config = get_live_config()
        tax_config = config.get("tax", {})
        
        # Fields to sync from config
        fields = [
            ("calculation_method", "tax_calculation_method", "Progressive"),
            ("use_ter", "use_ter", 0),
            ("use_gross_up", "use_gross_up", 0),
            ("npwp_mandatory", "npwp_mandatory", 0),
            ("biaya_jabatan_percent", "biaya_jabatan_percent", 5.0),
            ("biaya_jabatan_max", "biaya_jabatan_max", 500000.0),
        ]
        
        # Update fields via db_set to avoid triggering validate
        for field, config_field, default in fields:
            value = tax_config.get(config_field, default)
            if hasattr(self, field) and self.get(field) != value:
                self.db_set(field, value, update_modified=False)
                
        # Update modified timestamp
        self.db_set("modified", now_datetime(), update_modified=False)
        frappe.db.commit()
        
        logger.info("Settings updated from central configuration")
    
    @safe_execute(log_exception=True)
    def _sync_to_payroll_settings(self):
        """Sync changes to Payroll Indonesia Settings."""
        # Only sync if Payroll Indonesia Settings exists
        if not frappe.db.exists("DocType", "Payroll Indonesia Settings"):
            return
            
        try:
            # Get Payroll Indonesia Settings
            pi_settings = frappe.get_doc("Payroll Indonesia Settings", "Payroll Indonesia Settings")
            
            # Fields to sync to Payroll Indonesia Settings
            fields_to_sync = {
                "tax_calculation_method": self.calculation_method,
                "use_ter": self.use_ter,
                "use_gross_up": self.use_gross_up,
                "npwp_mandatory": self.npwp_mandatory,
                "biaya_jabatan_percent": self.biaya_jabatan_percent,
                "biaya_jabatan_max": self.biaya_jabatan_max,
            }
            
            # Check which fields need updating
            needs_update = False
            for field, value in fields_to_sync.items():
                if hasattr(pi_settings, field) and pi_settings.get(field) != value:
                    pi_settings.set(field, value)
                    needs_update = True
            
            # Save if changes were made
            if needs_update:
                pi_settings.flags.ignore_validate = True
                pi_settings.flags.ignore_permissions = True
                pi_settings.save(ignore_permissions=True)
                logger.info("Updated Payroll Indonesia Settings from PPh 21 Settings")
                
        except Exception as e:
            logger.error(f"Error syncing to Payroll Indonesia Settings: {str(e)}")


# Public function to update settings from configuration
@safe_execute(log_exception=True)
def update_from_config(doc=None):
    """Update PPh 21 Settings from configuration."""
    # Get document if not provided
    if not doc:
        if frappe.db.exists("PPh 21 Settings", "PPh 21 Settings"):
            doc = frappe.get_doc("PPh 21 Settings", "PPh 21 Settings")
        else:
            doc = frappe.new_doc("PPh 21 Settings")
    
    # Set flag to avoid recursion
    doc._updating_from_config = True
    
    try:
        # Update settings from configuration
        config = get_live_config()
        tax_config = config.get("tax", {})
        
        # Set basic fields
        doc.calculation_method = tax_config.get("tax_calculation_method", "Progressive")
        doc.use_ter = cint(tax_config.get("use_ter", 0))
        doc.use_gross_up = cint(tax_config.get("use_gross_up", 0))
        doc.npwp_mandatory = cint(tax_config.get("npwp_mandatory", 0))
        doc.biaya_jabatan_percent = flt(tax_config.get("biaya_jabatan_percent", 5.0))
        doc.biaya_jabatan_max = flt(tax_config.get("biaya_jabatan_max", 500000.0))
        
        # Save with ignore flags
        doc.flags.ignore_validate = True
        doc.flags.ignore_on_update = True
        doc.save(ignore_permissions=True)
        
        # Ensure tables are populated
        doc._ensure_tax_brackets()
        doc._ensure_ptkp_values()
        
        # Save again if needed
        if not doc.ptkp_table or not doc.bracket_table:
            doc.flags.ignore_validate = True
            doc.flags.ignore_on_update = True
            doc.save(ignore_permissions=True)
            
        logger.info("PPh 21 Settings updated from configuration")
        return doc
        
    finally:
        # Always reset flag
        doc._updating_from_config = False
