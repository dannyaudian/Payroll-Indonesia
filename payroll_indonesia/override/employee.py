# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Employee override module for Payroll Indonesia.

Provides a resilient Employee class extension that can adapt to path changes
in Frappe/ERPNext core code.
"""

import frappe
from frappe.model.document import Document
from payroll_indonesia.frappe_helpers import logger

# Define paths to try for Employee class import
PATHS_TO_TRY = [
    "hrms.hr.doctype.employee.employee.Employee",
    "erpnext.hr.doctype.employee.employee.Employee", 
    "erpnext.payroll.doctype.employee.employee.Employee",
    "hrms.payroll.doctype.employee.employee.Employee",
]

# Define what's publicly accessible
__all__ = ["EmployeeOverride", "validate", "on_update", "PATHS_TO_TRY"]


def _import_employee():
    """
    Dynamically import Employee class from various possible paths.
    
    Returns:
        class: Employee class if found, None otherwise
    """
    for path in PATHS_TO_TRY:
        try:
            module_path, cls_name = path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[cls_name])
            employee_class = getattr(module, cls_name)
            logger.info(f"Successfully imported Employee class from: {path}")
            return employee_class
        except ImportError:
            logger.debug(f"Could not import Employee from {path}")
            continue
        except Exception as e:
            logger.warning(f"Error importing from {path}: {str(e)}")
            continue
    
    logger.error("Could not import Employee class from any known path")
    return None


# Get the base Employee class or fall back to Document
BaseEmployee = _import_employee() or Document
logger.info(f"Using {BaseEmployee.__module__}.{BaseEmployee.__name__} as base class for EmployeeOverride")


class EmployeeOverride(BaseEmployee):
    """
    Override for Employee doctype.
    
    Extends the standard Employee doctype with Indonesian payroll specific functionality
    while being resilient to path changes in the core code.
    """
    
    def validate(self):
        """
        Validate Employee document.
        
        Calls parent validate if available and adds custom validation.
        """
        try:
            # Call parent validate if it exists
            if hasattr(super(), "validate"):
                super().validate()
            
            # Add custom validation for Indonesian payroll
            self._validate_indonesian_fields()
        except Exception as e:
            logger.exception(f"Error in EmployeeOverride.validate: {str(e)}")
            frappe.throw(f"Error validating employee: {str(e)}")
    
    def on_update(self):
        """
        Process after Employee document update.
        
        Calls parent on_update if available and performs custom actions.
        """
        try:
            # Call parent on_update if it exists
            if hasattr(super(), "on_update"):
                super().on_update()
            
            # Add custom on_update logic for Indonesian payroll
            self._update_related_records()
        except Exception as e:
            logger.exception(f"Error in EmployeeOverride.on_update: {str(e)}")
    
    def _validate_indonesian_fields(self):
        """Validate Indonesia-specific employee fields."""
        try:
            # Validate NPWP format if provided
            if hasattr(self, "npwp") and self.npwp:
                # NPWP format validation could go here
                pass
            
            # Validate KTP format if provided
            if hasattr(self, "ktp") and self.ktp:
                # KTP format validation could go here
                pass
            
            # Validate status pajak is valid
            if hasattr(self, "status_pajak") and self.status_pajak:
                valid_status = [
                    "TK0", "TK1", "TK2", "TK3", 
                    "K0", "K1", "K2", "K3", 
                    "HB0", "HB1", "HB2", "HB3"
                ]
                if self.status_pajak not in valid_status:
                    frappe.msgprint(
                        f"Status pajak '{self.status_pajak}' tidak valid. "
                        f"Gunakan salah satu dari: {', '.join(valid_status)}",
                        indicator="red"
                    )
        except Exception as e:
            logger.exception(f"Error validating Indonesian fields: {str(e)}")
    
    def _update_related_records(self):
        """Update related records after employee changes."""
        try:
            # Update logic could go here
            pass
        except Exception as e:
            logger.exception(f"Error updating related records: {str(e)}")


# Module-level hook wrappers for doc_events
def validate(doc, method=None):
    """
    Validate hook for Employee document.
    
    Args:
        doc: The Employee document
        method: The method that triggered this hook (unused)
    """
    try:
        doc.validate()
    except Exception as e:
        logger.exception(f"Error in validate hook: {str(e)}")
        frappe.throw(f"Error validating employee: {str(e)}")


def on_update(doc, method=None):
    """
    On update hook for Employee document.
    
    Args:
        doc: The Employee document
        method: The method that triggered this hook (unused)
    """
    try:
        doc.on_update()
    except Exception as e:
        logger.exception(f"Error in on_update hook: {str(e)}")