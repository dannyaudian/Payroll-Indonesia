# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-26 18:55:42 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document


class EmployeeMonthlyTaxDetail(Document):
    def validate(self):
        """Validate monthly tax detail entries"""
        self.validate_month()
        self.validate_amounts()

    def validate_month(self):
        """Validate that month is between 1 and 12"""
        if self.month < 1 or self.month > 12:
            frappe.throw(frappe._("Month must be between 1 and 12"))

    def validate_amounts(self):
        """Validate amount fields"""
        # Ensure all monetary fields are positive or zero
        for field in ["gross_pay", "bpjs_deductions", "other_deductions", "tax_amount"]:
            if hasattr(self, field) and getattr(self, field) < 0:
                frappe.throw(frappe._(f"{field.replace('_', ' ').title()} cannot be negative"))

    def on_update(self):
        """Actions when monthly tax detail is updated"""
        # If TER is not used, ensure TER rate is 0
        if not self.is_using_ter and self.ter_rate != 0:
            self.ter_rate = 0

        # Notify parent document of changes if needed
        if self.parent:
            parent_doc = frappe.get_doc("Employee Tax Summary", self.parent)
            if parent_doc:
                parent_doc.flags.ignore_validate_update_after_submit = True
                parent_doc.calculate_ytd_from_monthly()
                parent_doc.db_update()
