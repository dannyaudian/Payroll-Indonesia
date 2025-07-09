# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PTKPTableEntry(Document):
    def validate(self):
        """Validate PTKP Table Entry"""
        self.validate_ptkp_amount()

    def validate_ptkp_amount(self):
        """Validate PTKP amount is non-negative"""
        if self.ptkp_amount < 0:
            frappe.throw(
                frappe._("PTKP Amount cannot be negative for {0}").format(self.status_pajak)
            )
