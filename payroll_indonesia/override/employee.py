# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Employee override module for Payroll Indonesia.

Provides a resilient Employee class extension that can adapt to path changes
in Frappe/ERPNext core code.
"""

import inspect
import sys
from typing import Any, Dict, List, Optional, Type, Tuple

import frappe
from frappe import _
from frappe.model.document import Document
from payroll_indonesia.frappe_helpers import logger

# Define paths to try for Employee class import
PATHS_TO_TRY = [
    "hrms.hr.doctype.employee.employee.Employee",
    "hrms.payroll.doctype.employee.employee.Employee",
    "erpnext.hr.doctype.employee.employee.Employee",
    "erpnext.payroll.doctype.employee.employee.Employee",
]

# Define what's publicly accessible
__all__ = ["EmployeeOverride", "validate", "on_update", "PATHS_TO_TRY"]


def _import_employee() -> Optional[Type]:
    """
    Dynamically import Employee class from various possible paths.
    
    Returns:
        Type: Employee class if found, None otherwise
    """
    errors = []
    employee_classes = []
    
    # Try each path
    for path in PATHS_TO_TRY:
        try:
            module_path, cls_name = path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[cls_name])
            employee_class = getattr(module, cls_name)
            
            # Verify it's a proper Document subclass
            if (inspect.isclass(employee_class) and 
                issubclass(employee_class, Document) and
                employee_class.__name__ == "Employee"):
                logger.info(f"Successfully imported Employee class from: {path}")
                employee_classes.append((path, employee_class))
        except ImportError as e:
            errors.append(f"ImportError for {path}: {str(e)}")
        except AttributeError as e:
            errors.append(f"AttributeError for {path}: {str(e)}")
        except Exception as e:
            errors.append(f"Error {type(e).__name__} for {path}: {str(e)}")
    
    # If we found at least one class, use the first one
    if employee_classes:
        path, employee_class = employee_classes[0]
        logger.info(f"Using Employee class from {path}")
        return employee_class
    
    # Log detailed error info
    error_details = "\n".join(errors)
    advice = (
        "Make sure one of these apps is installed: hrms, erpnext. "
        "Check if the Employee doctype exists and is properly defined."
    )
    logger.error(
        f"Could not import Employee class from any known path:\n{error_details}\n{advice}"
    )
    return None


# Get the base Employee class or fall back to Document
BaseEmployee = _import_employee() or Document

if BaseEmployee is Document:
    logger.warning(
        "Falling back to frappe.model.document.Document as base class. "
        "This means the Employee class could not be found in any known location. "
        "Some functionality may be limited."
    )
else:
    logger.info(f"Using {BaseEmployee.__module__}.{BaseEmployee.__name__} as base class")


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
            # Call parent validate if Employee class was found
            if BaseEmployee is not Document:
                try:
                    super().validate()
                    logger.debug(f"Called parent validate for {self.name}")
                except Exception as e:
                    logger.warning(
                        f"Error calling parent validate for {self.name}: {str(e)}. "
                        f"Continuing with custom validation."
                    )
            else:
                logger.debug(
                    f"Skipping parent validate for {self.name} (no Employee class found)"
                )
            
            # Always run custom validation regardless of parent class
            self._validate_indonesian_fields()
            logger.debug(f"Completed custom validation for {self.name}")
            
        except Exception as e:
            logger.exception(f"Error in EmployeeOverride.validate for {self.name}: {str(e)}")
            frappe.msgprint(
                _("Error validating employee {0}: {1}").format(self.name, str(e)),
                indicator="red"
            )
    
    def on_update(self):
        """
        Process after Employee document update.
        
        Calls parent on_update if available and performs custom actions.
        """
        try:
            # Call parent on_update if Employee class was found
            if BaseEmployee is not Document:
                try:
                    super().on_update()
                    logger.debug(f"Called parent on_update for {self.name}")
                except Exception as e:
                    logger.warning(
                        f"Error calling parent on_update for {self.name}: {str(e)}. "
                        f"Continuing with custom logic."
                    )
            else:
                logger.debug(
                    f"Skipping parent on_update for {self.name} (no Employee class found)"
                )
            
            # Always run custom logic regardless of parent class
            self._update_related_records()
            logger.debug(f"Completed custom on_update logic for {self.name}")
            
        except Exception as e:
            logger.exception(f"Error in EmployeeOverride.on_update for {self.name}: {str(e)}")
    
    def _validate_indonesian_fields(self):
        """
        Validate Indonesia-specific employee fields.
        
        Checks NPWP, KTP, status pajak, and other Indonesia-specific fields.
        """
        try:
            # Check if status_pajak exists and is valid
            if hasattr(self, "status_pajak") and self.status_pajak:
                valid_status = [
                    "TK0", "TK1", "TK2", "TK3", 
                    "K0", "K1", "K2", "K3", 
                    "HB0", "HB1", "HB2", "HB3"
                ]
                
                if self.status_pajak not in valid_status:
                    frappe.msgprint(
                        _("Status pajak '{0}' tidak valid. Gunakan salah satu dari: {1}").format(
                            self.status_pajak, ", ".join(valid_status)
                        ),
                        indicator="red"
                    )
            
            # Validate NPWP format if provided
            if hasattr(self, "npwp") and self.npwp:
                # Just a basic length check for now
                if len(self.npwp.replace(".", "").replace("-", "")) != 15:
                    frappe.msgprint(
                        _("Format NPWP tidak valid. NPWP harus 15 digit."),
                        indicator="yellow"
                    )
            
            # Validate KTP format if provided
            if hasattr(self, "ktp") and self.ktp:
                # Just a basic length check for now
                if len(self.ktp.replace(".", "").replace("-", "")) != 16:
                    frappe.msgprint(
                        _("Format KTP tidak valid. KTP harus 16 digit."),
                        indicator="yellow"
                    )
            
            # Check jumlah_tanggungan is consistent with status_pajak
            if (hasattr(self, "status_pajak") and self.status_pajak and 
                hasattr(self, "jumlah_tanggungan")):
                # Extract the number from status
                if len(self.status_pajak) >= 2:
                    status_num = self.status_pajak[-1]
                    if status_num.isdigit():
                        expected_tanggungan = int(status_num)
                        if self.jumlah_tanggungan != expected_tanggungan:
                            self.jumlah_tanggungan = expected_tanggungan
                            logger.debug(
                                f"Updated jumlah_tanggungan to {expected_tanggungan} "
                                f"based on status_pajak {self.status_pajak}"
                            )
            
        except Exception as e:
            logger.exception(f"Error validating Indonesian fields for {self.name}: {str(e)}")
    
    def _update_related_records(self):
        """
        Update related records after employee changes.
        
        Updates payroll-related records when employee data changes.
        """
        try:
            # Update BPJS enrollment status
            self._sync_bpjs_enrollment()
            
            # Update tax-related records if status_pajak changed
            self._sync_tax_status()
            
        except Exception as e:
            logger.exception(f"Error updating related records for {self.name}: {str(e)}")
    
    def _sync_bpjs_enrollment(self):
        """Sync BPJS enrollment status with related records."""
        pass  # Placeholder for actual implementation
    
    def _sync_tax_status(self):
        """Sync tax status with related records."""
        pass  # Placeholder for actual implementation


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
        logger.exception(f"Error in validate hook for {doc.name}: {str(e)}")
        frappe.msgprint(
            _("Error validating employee {0}: {1}").format(doc.name, str(e)),
            indicator="red"
        )


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
        logger.exception(f"Error in on_update hook for {doc.name}: {str(e)}")