# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 08:09:23 by dannyaudian

import frappe
from frappe import _
from frappe.model.document import Document

# Fix: Use dynamic import approach to avoid direct import error
Employee = None
try:
    # Try HRMS v15 path first
    from hrms.hr.doctype.employee.employee import Employee
except ImportError:
    try:
        # Fallback to older path (for compatibility)
        from hrms.payroll.doctype.employee.employee import Employee
    except ImportError:
        # If both fail, log error but don't crash on import
        frappe.log_error("Could not import Employee class - path may have changed", "Import Error")

__all__ = ["EmployeeOverride", "validate", "on_update", "create_custom_fields"]


class EmployeeOverride(Document):
    """
    Custom Employee class for Payroll Indonesia.
    Using Document as base class to avoid import errors.
    """
    
    def validate(self):
        # Call parent validation if possible
        if Employee and issubclass(self.__class__, Employee):
            super().validate()
        
        # Perform our custom validation
        validate(self)


def validate(doc, method=None):
    """Validate employee fields for Indonesian payroll"""
    try:
        # Validate status_pajak if set
        if doc.get("status_pajak"):
            # Ensure jumlah_tanggungan matches status_pajak
            status = doc.get("status_pajak", "")
            tanggungan = doc.get("jumlah_tanggungan", 0)

            if status and len(status) >= 2:
                try:
                    # Get last digit from status (e.g., TK0, K3)
                    status_tanggungan = int(status[-1])

                    if status_tanggungan != tanggungan:
                        doc.jumlah_tanggungan = status_tanggungan
                        frappe.msgprint(
                            _("Jumlah tanggungan disesuaikan dengan status pajak."),
                            indicator="blue",
                        )
                except (ValueError, IndexError):
                    # Non-critical error - we can continue with existing value
                    frappe.log_error(
                        "Invalid status_pajak format: {0}. Expected format like TK0 or K1.".format(
                            status
                        ),
                        "Employee Validation Warning",
                    )
                    frappe.msgprint(
                        _("Status Pajak has invalid format. Expected format like TK0 or K1."),
                        indicator="orange",
                    )

        # Validate NPWP Gabung Suami - critical validation
        if doc.get("npwp_gabung_suami") and not doc.get("npwp_suami"):
            frappe.throw(
                _("NPWP Suami harus diisi jika NPWP Gabung Suami dipilih."),
                title=_("NPWP Validation Failed"),
            )

        # Validate KTP (if applicable)
        if doc.get("ktp") and len(str(doc.get("ktp")).replace(" ", "")) != 16:
            frappe.msgprint(
                _("KTP should be 16 digits. Current format may be incorrect."),
                indicator="orange",
            )

    except Exception as e:
        # Handle ValidationError separately - don't catch these
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # For unexpected errors, log and re-raise
        frappe.log_error(
            "Error validating Employee {0}: {1}".format(
                doc.name if hasattr(doc, "name") else "", str(e)
            ),
            "Employee Validation Error",
        )
        frappe.throw(
            _("An error occurred during employee validation: {0}").format(str(e)),
            title=_("Validation Error"),
        )


def on_update(doc, method=None):
    """Additional actions when employee is updated"""
    pass


def create_custom_fields():
    """
    Create custom fields for Employee doctype based on custom_fields.json.
    
    This function doesn't need to define all fields manually as they'll be created
    from the JSON fixture file during migration/setup.
    """
    try:
        from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
        
        # Only create critical fields that might be needed before fixture sync
        custom_fields = {
            "Employee": [
                {
                    "fieldname": "payroll_indo_main_section",
                    "fieldtype": "Section Break",
                    "label": "Payroll Indonesia",
                    "insert_after": "reports_to",
                    "collapsible": 0,
                },
                {
                    "fieldname": "status_pajak",
                    "fieldtype": "Select",
                    "label": "Status Pajak",
                    "options": "TK0\nTK1\nTK2\nTK3\nK0\nK1\nK2\nK3\nHB0\nHB1\nHB2\nHB3",
                    "insert_after": "jabatan",
                },
                {
                    "fieldname": "npwp",
                    "fieldtype": "Data",
                    "label": "NPWP",
                    "insert_after": "identifier_section",
                    "in_standard_filter": 1,
                },
            ]
        }

        # Create minimal fields - full set will come from fixtures
        create_custom_fields(custom_fields)
        frappe.msgprint(
            _("Basic Payroll Indonesia custom fields created. Full set will be created from fixtures."),
            alert=True
        )
        
        return True

    except Exception as e:
        # This is a non-critical error during setup - log and notify
        frappe.log_error(
            "Error creating custom fields for Indonesian Payroll: {0}".format(str(e)),
            "Custom Field Creation Error",
        )
        frappe.msgprint(
            _(
                "Warning: Could not create all custom fields for Indonesian Payroll. See error log for details."
            ),
            indicator="orange",
        )
        return False


def reload_doctype():
    """
    Reload the Employee DocType.
    This can be called after custom fields are created to ensure they're visible.
    """
    try:
        frappe.reload_doctype("Employee")
        return True
    except Exception as e:
        frappe.log_error(f"Error reloading Employee doctype: {str(e)}", "DocType Reload Error")
        return False