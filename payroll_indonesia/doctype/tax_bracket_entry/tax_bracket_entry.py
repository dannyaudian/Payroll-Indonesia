# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TaxBracketEntry(Document):
    def validate(self):
        """Validate Tax Bracket Entry"""
        self.validate_income_range()
        self.validate_tax_rate()

    def validate_income_range(self):
        """Validate income_from and income_to values"""
        if self.income_from < 0:
            frappe.throw(frappe._("Income From cannot be negative"))

        if self.income_to < 0:
            frappe.throw(frappe._("Income To cannot be negative"))

        if self.income_to > 0 and self.income_from >= self.income_to:
            frappe.throw(
                frappe._("Income From must be less than Income To for non-highest brackets")
            )

    def validate_tax_rate(self):
        """Validate tax rate is within reasonable range"""
        if self.tax_rate < 0:
            frappe.throw(frappe._("Tax Rate cannot be negative"))

        if self.tax_rate > 100:
            frappe.msgprint(
                frappe._("Tax Rate is unusually high at {0}%").format(self.tax_rate),
                indicator="orange",
            )
