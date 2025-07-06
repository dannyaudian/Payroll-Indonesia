# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 08:09:23 by dannyaudian

import frappe
from frappe import _

# Fix the import path for HRMS v15
from hrms.hr.doctype.employee.employee import Employee

__all__ = ["EmployeeOverride", "validate", "on_update", "create_custom_fields"]


class EmployeeOverride(Employee):
    """Custom Employee class for Payroll Indonesia."""

    pass


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
    Create custom fields for Employee doctype
    
    This method creates custom fields based on the custom_fields.json file
    with minimal hardcoding for better maintainability.
    """
    try:
        from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

        # Base fields from the JSON file structure
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
                    "fieldname": "golongan",
                    "fieldtype": "Link",
                    "label": "Golongan",
                    "options": "Golongan",
                    "insert_after": "payroll_indo_main_section",
                    "in_list_view": 1,
                    "in_standard_filter": 1,
                },
                {
                    "fieldname": "jabatan",
                    "fieldtype": "Link",
                    "label": "Jabatan",
                    "options": "Jabatan",
                    "insert_after": "branch",
                },
                {
                    "fieldname": "status_pajak",
                    "fieldtype": "Select",
                    "label": "Status Pajak",
                    "options": "TK0\nTK1\nTK2\nTK3\nK0\nK1\nK2\nK3\nHB0\nHB1\nHB2\nHB3",
                    "insert_after": "jabatan",
                },
                {
                    "fieldname": "jumlah_tanggungan",
                    "fieldtype": "Int",
                    "label": "Jumlah Tanggungan",
                    "insert_after": "status_pajak",
                    "read_only": 1,
                },
                {
                    "fieldname": "override_tax_method",
                    "fieldtype": "Select",
                    "label": "Override Tax Method",
                    "options": "\nProgressive\nTER",
                    "insert_after": "jumlah_tanggungan",
                },
                {
                    "fieldname": "payroll_id_col_break_1",
                    "fieldtype": "Column Break",
                    "insert_after": "override_tax_method",
                },
                {
                    "fieldname": "tipe_karyawan",
                    "fieldtype": "Select",
                    "label": "Tipe Karyawan",
                    "options": "Tetap\nTidak Tetap\nFreelance",
                    "insert_after": "payroll_id_col_break_1",
                },
                {
                    "fieldname": "penghasilan_final",
                    "fieldtype": "Check",
                    "label": "Penghasilan Final",
                    "insert_after": "tipe_karyawan",
                    "description": "PPh 21 final - tidak dipotong setiap bulan",
                    "default": "0",
                },
                {
                    "fieldname": "identifier_section",
                    "fieldtype": "Section Break",
                    "label": "Identifiers & Attachments",
                    "insert_after": "penghasilan_final",
                    "collapsible": 0,
                },
                {
                    "fieldname": "npwp",
                    "fieldtype": "Data",
                    "label": "NPWP",
                    "insert_after": "identifier_section",
                    "in_standard_filter": 1,
                },
                {
                    "fieldname": "upload_npwp",
                    "fieldtype": "Attach",
                    "label": "Upload NPWP",
                    "insert_after": "npwp",
                },
                {
                    "fieldname": "ktp",
                    "fieldtype": "Data",
                    "label": "KTP",
                    "insert_after": "upload_npwp",
                    "in_standard_filter": 1,
                },
                {
                    "fieldname": "upload_ktp",
                    "fieldtype": "Attach",
                    "label": "Upload KTP",
                    "insert_after": "ktp",
                },
                {
                    "fieldname": "identifier_col_break",
                    "fieldtype": "Column Break",
                    "insert_after": "upload_ktp",
                },
                {
                    "fieldname": "npwp_suami",
                    "fieldtype": "Data",
                    "label": "NPWP Suami",
                    "insert_after": "identifier_col_break",
                    "depends_on": "eval:doc.gender=='Female'",
                },
                {
                    "fieldname": "npwp_gabung_suami",
                    "fieldtype": "Check",
                    "label": "NPWP Gabung Suami",
                    "insert_after": "npwp_suami",
                    "depends_on": "eval:doc.gender=='Female'",
                    "default": "0",
                },
                {
                    "fieldname": "bpjs_enrollment_section",
                    "fieldtype": "Section Break",
                    "label": "BPJS Enrollment",
                    "insert_after": "npwp_gabung_suami",
                    "collapsible": 0,
                },
                {
                    "fieldname": "ikut_bpjs_kesehatan",
                    "fieldtype": "Check",
                    "label": "Ikut BPJS Kesehatan",
                    "insert_after": "bpjs_enrollment_section",
                    "default": "1",
                },
                {
                    "fieldname": "bpjs_kesehatan_id",
                    "fieldtype": "Data",
                    "label": "BPJS Kesehatan ID",
                    "insert_after": "ikut_bpjs_kesehatan",
                },
                {
                    "fieldname": "ikut_bpjs_ketenagakerjaan",
                    "fieldtype": "Check",
                    "label": "Ikut BPJS Ketenagakerjaan",
                    "insert_after": "bpjs_kesehatan_id",
                    "default": "1",
                },
                {
                    "fieldname": "bpjs_ketenagakerjaan_id",
                    "fieldtype": "Data",
                    "label": "BPJS Ketenagakerjaan ID",
                    "insert_after": "ikut_bpjs_ketenagakerjaan",
                },
            ]
        }

        # Create the custom fields
        create_custom_fields(custom_fields)
        frappe.msgprint(_("Payroll Indonesia custom fields created successfully"), alert=True)

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