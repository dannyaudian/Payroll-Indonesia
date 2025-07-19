# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
Payroll Entry - Main override for Indonesia-specific payroll processing
"""

import logging
import inspect
from typing import Dict, List, Tuple, Any, Optional, Union, Type
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
from payroll_indonesia.utilities.field_accessor import PayrollEntryFieldAccessor

# Paths to try for importing the core PayrollEntry class
PAYROLL_ENTRY_PATHS = [
    "hrms.payroll.doctype.payroll_entry.payroll_entry.PayrollEntry",
    "hrms.hr.doctype.payroll_entry.payroll_entry.PayrollEntry",
    "erpnext.payroll.doctype.payroll_entry.payroll_entry.PayrollEntry",
    "erpnext.hr.doctype.payroll_entry.payroll_entry.PayrollEntry",
]


def _import_payroll_entry() -> Optional[Type]:
    """Attempt to dynamically import PayrollEntry class from various paths."""
    errors = []
    for path in PAYROLL_ENTRY_PATHS:
        try:
            module_path, cls_name = path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[cls_name])
            payroll_entry_cls = getattr(module, cls_name)
            if (
                inspect.isclass(payroll_entry_cls)
                and issubclass(payroll_entry_cls, Document)
                and payroll_entry_cls.__name__ == "PayrollEntry"
            ):
                logger.info(f"Successfully imported PayrollEntry class from: {path}")
                return payroll_entry_cls
        except ImportError as e:
            errors.append(f"ImportError for {path}: {str(e)}")
        except AttributeError as e:
            errors.append(f"AttributeError for {path}: {str(e)}")
        except Exception as e:
            errors.append(f"Error {type(e).__name__} for {path}: {str(e)}")

    if errors:
        logger.error(
            "Could not import PayrollEntry class from any known path:\n" + "\n".join(errors)
        )
    return None


# Use imported PayrollEntry if available, otherwise fall back to Document
BasePayrollEntry = _import_payroll_entry() or Document

if BasePayrollEntry is Document:
    logger.warning(
        "Falling back to frappe.model.document.Document as base class. "
        "This means the PayrollEntry class could not be found in any known location."
    )
else:
    logger.info(
        f"Using {BasePayrollEntry.__module__}.{BasePayrollEntry.__name__} as base class"
    )

class CustomPayrollEntry(BasePayrollEntry):
    """
    Custom Payroll Entry class for Indonesia-specific payroll functionality.
    """
    
    def validate(self):
        """
        Validate the document before saving.
        """
        try:
            if BasePayrollEntry is not Document:
                try:
                    super().validate()
                    logger.debug(
                        f"Called parent validate for {getattr(self, 'name', 'unknown')}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Error calling parent validate for {getattr(self, 'name', 'unknown')}: {str(e)}. "
                        f"Continuing with custom validation."
                    )
            else:
                logger.debug(
                    f"Skipping parent validate for {getattr(self, 'name', 'unknown')} (no PayrollEntry class found)"
                )

            self.validate_tax_settings()

        except Exception as e:
            logger.exception(
                f"Error in CustomPayrollEntry.validate for {getattr(self, 'name', 'unknown')}: {str(e)}"
            )
    
    def validate_tax_settings(self):
        """
        Validate tax-related settings.
        """
        try:
            accessor = PayrollEntryFieldAccessor(self)

            # Skip if Indonesia payroll not enabled
            if not accessor.is_indonesia_tax_enabled():
                return
            
            # Validate tax method
            tax_method = accessor.get("tax_method", "Progressive")
            if tax_method not in ["Progressive", "TER"]:
                frappe.throw(_("Invalid tax method. Must be 'Progressive' or 'TER'."))
            
            # If using TER, ensure TER settings are defined
            if tax_method == "TER" or accessor.is_ter_method_enabled():
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
    
class TaxSettingsPropagatorMixin:
    """Mixin providing tax settings propagation logic."""

    def propagate_tax_settings_to_slips(self, slips):
        """Propagate payroll entry tax settings to the given salary slips."""
        try:
            doc = getattr(self, "doc", self)
            if not doc or not slips:
                return

            if cint(getattr(doc, "calculate_indonesia_tax", 0)) != 1:
                return

            tax_method = getattr(doc, "tax_method", "Progressive")
            if cint(getattr(doc, "ter_method_enabled", 0)) == 1:
                tax_method = "TER"

            settings = {
                "calculate_indonesia_tax": 1,
                "tax_method": tax_method,
                "is_december_override": cint(getattr(doc, "is_december_override", 0)),
            }

            for slip in slips:
                for field, value in settings.items():
                    if hasattr(slip, field):
                        setattr(slip, field, value)

            logger.debug(f"Propagated tax settings to {len(slips)} salary slips")

        except Exception as e:
            logger.exception(f"Error propagating tax settings: {str(e)}")


class CustomPayrollEntry(TaxSettingsPropagatorMixin, BasePayrollEntry):
    """Custom Payroll Entry class for Indonesia-specific payroll functionality."""
    
    def create_salary_slips(self):
        """
        Override to ensure proper Indonesia tax settings are propagated.
        """
        try:
            # Log entry point
            logger.info(f"Creating salary slips for payroll entry {self.name}")

            # Set Indonesia tax flag if enabled
            if not hasattr(self, "calculate_indonesia_tax"):
                self.calculate_indonesia_tax = 1

            # Call parent method (either standard version or with super())
            if BasePayrollEntry is not Document:
                result = super().create_salary_slips()
            else:
                # Fallback if parent class not properly detected
                result = self.create_salary_slip_standard()

            # After slips are created, get them and update tax settings
            slip_names = frappe.get_all(
                "Salary Slip",
                filters={"payroll_entry": self.name},
                pluck="name"
            )

            if slip_names:
                logger.info(f"Found {len(slip_names)} salary slips to update")
                slips = [frappe.get_doc("Salary Slip", name) for name in slip_names]
                self.propagate_tax_settings_to_slips(slips)

                # Save all slips
                for slip in slips:
                    slip.flags.ignore_validate = True
                    slip.save()

                logger.info(f"Updated tax settings for {len(slips)} salary slips")
            else:
                logger.warning("No salary slips found to update tax settings")

            return result
        except Exception as e:
            logger.exception(f"Error in create_salary_slips: {str(e)}")
            frappe.log_error(
                f"Error in create_salary_slips: {str(e)}",
                "Payroll Entry Indonesia"
            )
            # Re-raise to maintain original behavior
            raise

    def submit_salary_slips(self):
        """
        Override to ensure proper Indonesia tax settings before submission.
        """
        try:
            logger.info(f"Submitting salary slips for payroll entry {self.name}")

            # Get all unsubmitted slips
            slip_names = frappe.get_all(
                "Salary Slip",
                filters={
                    "payroll_entry": self.name,
                    "docstatus": 0  # Draft
                },
                pluck="name"
            )

            if slip_names:
                logger.info(f"Found {len(slip_names)} salary slips to update before submission")
                slips = [frappe.get_doc("Salary Slip", name) for name in slip_names]

                # Update tax settings once more
                self.propagate_tax_settings_to_slips(slips)

                # Save all slips before submission
                for slip in slips:
                    # Force tax calculation
                    if hasattr(slip, "calculate_tax"):
                        try:
                            slip.calculate_tax()
                        except Exception as calc_error:
                            logger.warning(f"Error calculating tax for slip {slip.name}: {str(calc_error)}")

                    slip.flags.ignore_validate = True
                    slip.save()

                logger.info(f"Updated tax settings for {len(slips)} salary slips before submission")

            # Call parent method
            if BasePayrollEntry is not Document:
                return super().submit_salary_slips()
            else:
                # Fallback implementation
                return self.submit_salary_slips_standard()

        except Exception as e:
            logger.exception(f"Error in submit_salary_slips: {str(e)}")
            frappe.log_error(
                f"Error in submit_salary_slips: {str(e)}",
                "Payroll Entry Indonesia"
            )
            # Re-raise to maintain original behavior
            raise
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


class PayrollEntryIndonesia(TaxSettingsPropagatorMixin):
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
