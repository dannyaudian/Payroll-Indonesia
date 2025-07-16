# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Field accessor utility for safely handling custom fields.
Provides validation and defaulting mechanisms.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from payroll_indonesia.schema.custom_fields import SalarySlipSchema, PayrollEntrySchema, EmployeeSchema

class FieldAccessor:
    """Base field accessor for safe field access"""
    
    def __init__(self, doc, schema_class):
        """
        Initialize accessor with document and schema
        
        Args:
            doc: Document to access fields from
            schema_class: Schema class for validation
        """
        self.doc = doc
        self.schema = schema_class
    
    def get(self, field_name, default=None):
        """
        Get field value safely with validation
        
        Args:
            field_name: Name of the field to get
            default: Default value if field doesn't exist
            
        Returns:
            Field value or default
        """
        # Check if field exists in document
        if hasattr(self.doc, field_name):
            value = getattr(self.doc, field_name)
            
            # If value is None or empty, use default
            if value is None or value == "":
                # Try schema default first, then provided default
                schema_default = self.schema.get_default(field_name)
                return schema_default if schema_default is not None else default
            
            return value
        
        # Field doesn't exist, use schema default or provided default
        schema_default = self.schema.get_default(field_name)
        return schema_default if schema_default is not None else default
    
    def set(self, field_name, value):
        """
        Set field value safely with validation
        
        Args:
            field_name: Name of the field to set
            value: Value to set
            
        Returns:
            True if successful, False otherwise
        """
        # Validate against schema if field is defined
        if field_name in self.schema.FIELDS:
            is_valid, error = self.schema.validate(self.doc, field_name, value)
            if not is_valid:
                frappe.log_error(
                    f"Invalid value for {field_name}: {error}",
                    "Field Validation Error"
                )
                return False
        
        # Set the field
        setattr(self.doc, field_name, value)
        return True
    
    def update(self, fields_dict):
        """
        Update multiple fields at once
        
        Args:
            fields_dict: Dictionary of field name to value mappings
            
        Returns:
            List of fields that were successfully updated
        """
        updated = []
        for field_name, value in fields_dict.items():
            if self.set(field_name, value):
                updated.append(field_name)
        
        return updated


class SalarySlipFieldAccessor(FieldAccessor):
    """Field accessor specifically for Salary Slip documents"""
    
    def __init__(self, doc):
        super().__init__(doc, SalarySlipSchema)
    
    def get_tax_method(self):
        """Get tax method with proper defaulting and validation"""
        method = self.get("tax_method", "Progressive")
        if method not in ["Progressive", "TER"]:
            frappe.log_error(
                f"Invalid tax method '{method}' for {self.doc.name}, using Progressive",
                "Tax Method Error"
            )
            return "Progressive"
        return method
    
    def get_status_pajak(self):
        """Get tax status with proper defaulting and validation"""
        status = self.get("status_pajak")
        
        # If not set, try to get from employee
        if not status:
            employee = getattr(self.doc, "employee_doc", None)
            if not employee and hasattr(self.doc, "employee"):
                try:
                    employee = frappe.get_doc("Employee", self.doc.employee)
                    self.doc.employee_doc = employee
                except Exception:
                    pass
            
            if employee and hasattr(employee, "status_pajak") and employee.status_pajak:
                status = employee.status_pajak
                # Update the document
                self.set("status_pajak", status)
        
        # Validate the status
        valid_statuses = SalarySlipSchema.FIELDS["status_pajak"]["options"]
        if status not in valid_statuses:
            frappe.log_error(
                f"Invalid tax status '{status}' for {self.doc.name}, using TK0",
                "Tax Status Error"
            )
            return "TK0"
        
        return status
    
    def is_december_calculation(self):
        """Check if this is a December calculation"""
        return cint(self.get("is_december_override", 0)) == 1


class PayrollEntryFieldAccessor(FieldAccessor):
    """Field accessor specifically for Payroll Entry documents"""
    
    def __init__(self, doc):
        super().__init__(doc, PayrollEntrySchema)
    
    def is_indonesia_tax_enabled(self):
        """Check if Indonesia tax calculation is enabled"""
        return cint(self.get("calculate_indonesia_tax", 0)) == 1
    
    def is_ter_method_enabled(self):
        """Check if TER method is enabled"""
        return cint(self.get("ter_method_enabled", 0)) == 1
    
    def is_december_override(self):
        """Check if December override is enabled"""
        return cint(self.get("is_december_override", 0)) == 1


class EmployeeFieldAccessor(FieldAccessor):
    """Field accessor specifically for Employee documents"""
    
    def __init__(self, doc):
        super().__init__(doc, EmployeeSchema)
    
    def get_status_pajak(self):
        """Get tax status with proper defaulting and validation"""
        status = self.get("status_pajak")
        
        # Validate the status
        valid_statuses = EmployeeSchema.FIELDS["status_pajak"]["options"]
        if status and status not in valid_statuses:
            frappe.log_error(
                f"Invalid tax status '{status}' for {self.doc.name}, using TK0",
                "Tax Status Error"
            )
            return "TK0"
        
        return status
    
    def is_bpjs_kesehatan_enrolled(self):
        """Check if employee is enrolled in BPJS Kesehatan"""
        return cint(self.get("ikut_bpjs_kesehatan", 1)) == 1
    
    def is_bpjs_ketenagakerjaan_enrolled(self):
        """Check if employee is enrolled in BPJS Ketenagakerjaan"""
        return cint(self.get("ikut_bpjs_ketenagakerjaan", 1)) == 1
