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
]

# Define what's publicly accessible
__all__ = ["EmployeeOverride", "validate", "on_update"]


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
            continue
        except Exception as e:
            logger.warning(f"Error importing from {path}: {str(e)}")
            continue
    
    logger.error("Could not import Employee class from any known path")
    return None


# Get the base Employee class or fall back to Document
BaseEmployee = _import_employee() or Document


class EmployeeOverride(BaseEmployee):
    """
    Override for Employee doctype.
    
    Extends the standard Employee doctype with Indonesian payroll specific functionality
    while being resilient to path changes in the core code.
    """
    
    def validate(self):
        """
        Validate Employee document.
        
        Calls parent validation if available and adds custom validation.
        """
        # Call parent validate if it exists
        if hasattr(super(), "validate"):
            super().validate()
        
        # Add custom validation for Indonesian payroll
        self._validate_indonesian_fields()
    
    def on_update(self):
        """
        Process after Employee document update.
        
        Calls parent on_update if available and performs custom actions.
        """
        # Call parent on_update if it exists
        if hasattr(super(), "on_update"):
            super().on_update()
        
        # Add custom on_update logic for Indonesian payroll
        self._update_related_records()
    
    def _validate_indonesian_fields(self):
        """Validate Indonesia-specific employee fields."""
        # Placeholder for custom validation logic
        pass
    
    def _update_related_records(self):
        """Update related records after employee changes."""
        # Placeholder for custom update logic
        pass


# Module-level hook wrappers for doc_events
def validate(doc, method=None):
    """
    Validate hook for Employee document.
    
    Args:
        doc: The Employee document
        method: The method that triggered this hook (unused)
    """
    doc.validate()


def on_update(doc, method=None):
    """
    On update hook for Employee document.
    
    Args:
        doc: The Employee document
        method: The method that triggered this hook (unused)
    """
    doc.on_update()