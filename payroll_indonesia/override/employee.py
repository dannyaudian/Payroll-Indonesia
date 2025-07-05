# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 08:09:23 by dannyaudian

import frappe
from frappe import _


def validate(doc, method):
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


def on_update(doc, method):
    """Additional actions when employee is updated"""
    pass


def create_custom_fields():
    """Create custom fields for Employee doctype"""
    try:
        from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

        custom_fields = {
            "Employee": [
                {
                    "fieldname": "payroll_indonesia_section",
                    "fieldtype": "Section Break",
                    "label": "Indonesian Payroll",
                    "insert_after": "attendance_device_id",
                    "collapsible": 1,
                },
                {
                    "fieldname": "golongan",
                    "fieldtype": "Link",
                    "label": "Golongan",
                    "options": "Golongan",
                    "insert_after": "payroll_indonesia_section",
                },
                {
                    "fieldname": "jabatan",
                    "fieldtype": "Link",
                    "label": "Jabatan",
                    "options": "Jabatan",
                    "insert_after": "golongan",
                },
                {
                    "fieldname": "status_pajak",
                    "fieldtype": "Select",
                    "label": "Status Pajak",
                    "options": "\nTK0\nTK1\nTK2\nTK3\nK0\nK1\nK2\nK3",
                    "insert_after": "jabatan",
                },
                {
                    "fieldname": "jumlah_tanggungan",
                    "fieldtype": "Int",
                    "label": "Jumlah Tanggungan",
                    "insert_after": "status_pajak",
                },
                {
                    "fieldname": "npwp",
                    "fieldtype": "Data",
                    "label": "NPWP",
                    "insert_after": "jumlah_tanggungan",
                },
                {
                    "fieldname": "npwp_suami",
                    "fieldtype": "Data",
                    "label": "NPWP Suami",
                    "insert_after": "npwp",
                    "depends_on": "eval:doc.gender=='Female'",
                },
                {
                    "fieldname": "npwp_gabung_suami",
                    "fieldtype": "Check",
                    "label": "NPWP Gabung Suami",
                    "insert_after": "npwp_suami",
                    "depends_on": "eval:doc.gender=='Female'",
                },
                {
                    "fieldname": "bpjs_col",
                    "fieldtype": "Column Break",
                    "insert_after": "npwp_gabung_suami",
                },
                {
                    "fieldname": "ikut_bpjs_kesehatan",
                    "fieldtype": "Check",
                    "label": "BPJS Kesehatan",
                    "default": 1,
                    "insert_after": "bpjs_col",
                },
                {
                    "fieldname": "ikut_bpjs_ketenagakerjaan",
                    "fieldtype": "Check",
                    "label": "BPJS Ketenagakerjaan",
                    "default": 1,
                    "insert_after": "ikut_bpjs_kesehatan",
                },
                {
                    "fieldname": "tipe_karyawan",
                    "fieldtype": "Select",
                    "label": "Tipe Karyawan",
                    "options": "Tetap\nTidak Tetap\nFreelance",
                    "insert_after": "ikut_bpjs_ketenagakerjaan",
                },
                {
                    "fieldname": "penghasilan_final",
                    "fieldtype": "Check",
                    "label": "Penghasilan Final",
                    "insert_after": "tipe_karyawan",
                    "description": "PPh 21 final - tidak dipotong setiap bulan",
                },
            ]
        }

        create_custom_fields(custom_fields)

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
