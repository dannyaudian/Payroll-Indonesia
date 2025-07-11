# payroll_indonesia/payroll_indonesia/doctype/employee_monthly_tax_detail/employee_monthly_tax_detail.py
# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Employee Monthly Tax Detail controller.

This module manages the monthly details of employee tax records, functioning as
a child table of Employee Tax Summary.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint

def log_info(message):
    frappe.log(message)

def log_error(message):
    frappe.log_error(message, "Employee Monthly Tax Detail Error")
class EmployeeMonthlyTaxDetail(Document):
    """
    Employee Monthly Tax Detail document representing a single month's tax data.
    """
    
    def validate(self):
        """Validate the monthly tax detail before saving."""
        self.validate_month()
        self.validate_amounts()
        self.validate_ter_data()
    
    def validate_month(self):
        """Ensure month value is between 1 and 12."""
        if not self.month or self.month < 1 or self.month > 12:
            frappe.throw(_("Month must be between 1 and 12"))
    
    def validate_amounts(self):
        """Ensure all monetary amounts are non-negative."""
        for field in [
            "gross_pay", 
            "tax_amount", 
            "bpjs_deductions_employee",
            "other_deductions"
        ]:
            if hasattr(self, field) and flt(getattr(self, field)) < 0:
                setattr(self, field, 0)
                frappe.msgprint(
                    _("Negative {0} was reset to 0").format(
                        _(field.replace("_", " ").title())
                    )
                )
    
    def validate_ter_data(self):
        """Ensure TER data is consistent."""
        if hasattr(self, "is_using_ter") and not cint(self.is_using_ter):
            self.ter_rate = 0
        
        if (
            hasattr(self, "is_using_ter") 
            and cint(self.is_using_ter) 
            and (flt(self.ter_rate) <= 0 or flt(self.ter_rate) > 50)
        ):
            frappe.msgprint(
                _("Invalid TER rate {0}% for month {1}").format(
                    self.ter_rate, self.month
                )
            )
    
    def on_update(self):
        """Trigger parent document update when this document changes."""
        try:
            if self.parent:
                parent_doc = frappe.get_doc("Employee Tax Summary", self.parent)
                if parent_doc:
                    parent_doc.flags.ignore_validate_update_after_submit = True
                    parent_doc.calculate_ytd_totals()
                    parent_doc.save()
        except Exception as e:
            log_error(f"Error updating parent from monthly detail {self.name}: {str(e)}")
