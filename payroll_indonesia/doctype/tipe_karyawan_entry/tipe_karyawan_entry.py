# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TipeKaryawanEntry(Document):
    def validate(self):
        """Validate Tipe Karyawan Entry"""
        self.validate_tipe_karyawan_name()

    def validate_tipe_karyawan_name(self):
        """Validate tipe karyawan name is not empty and reasonable"""
        if not self.tipe_karyawan:
            frappe.throw(frappe._("Tipe Karyawan cannot be empty"))

        if len(self.tipe_karyawan) < 2:
            frappe.msgprint(
                frappe._("Tipe Karyawan '{0}' is unusually short").format(self.tipe_karyawan),
                indicator="orange",
            )

        # Check for duplicates in the parent document
        parent = self.get_parent_doc()
        if parent:
            for entry in parent.tipe_karyawan:
                if entry.name != self.name and entry.tipe_karyawan == self.tipe_karyawan:
                    frappe.throw(
                        frappe._("Tipe Karyawan '{0}' already exists").format(self.tipe_karyawan)
                    )

    def get_parent_doc(self):
        """Get parent document if possible"""
        try:
            if self.parent and self.parenttype and self.parentfield:
                return frappe.get_doc(self.parenttype, self.parent)
        except Exception:
            pass
        return None
