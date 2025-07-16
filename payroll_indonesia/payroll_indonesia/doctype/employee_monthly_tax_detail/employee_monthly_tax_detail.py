# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Employee Monthly Tax Detail controller.

This module manages the monthly details of employee tax records, functioning as
a child table of Employee Tax Summary.
"""

import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint

from payroll_indonesia.frappe_helpers import get_logger

logger = get_logger("employee_monthly_tax_detail")

class EmployeeMonthlyTaxDetail(Document):
    """
    Employee Monthly Tax Detail document representing a single month's tax data.
    """
    
    def validate(self):
        """Validate the monthly tax detail before saving."""
        self.validate_month()
        self.validate_amounts()
        self.validate_ter_data()
        self.validate_tax_method()
    
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
            "other_deductions",
            "tax_correction",
            "taxable_components",
            "tax_deductions",
            "non_taxable_components",
            "taxable_natura",
            "non_taxable_natura",
            "biaya_jabatan",
            "netto",
            "annual_taxable_income",
            "annual_pkp"
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
            self.ter_category = ""
        
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
    
    def validate_tax_method(self):
        """Ensure tax method is valid and consistent with TER settings."""
        if hasattr(self, "tax_method") and hasattr(self, "is_using_ter"):
            if self.tax_method == "TER" and not cint(self.is_using_ter):
                self.is_using_ter = 1
            elif self.tax_method == "Progressive" and cint(self.is_using_ter):
                self.is_using_ter = 0
                self.ter_rate = 0
                self.ter_category = ""
    
    def update_parent(self):
        """Update parent document after changes to this detail."""
        try:
            if self.parent:
                parent_doc = frappe.get_doc("Employee Tax Summary", self.parent)
                if parent_doc:
                    parent_doc.flags.ignore_validate_update_after_submit = True
                    parent_doc.update_totals()
                    parent_doc.save()
        except Exception as e:
            logger.error(f"Error updating parent from monthly detail: {str(e)}")
    
    def on_update(self):
        """Trigger parent document update when this document changes."""
        original_creation = frappe.db.get_value(self.doctype, self.name, "creation")
        self.update_parent()
        if original_creation and self.creation != original_creation:
            logger.warning(
                f"Creation timestamp mismatch for {self.name}. Resetting to original value"
            )
            self.creation = original_creation

    def get_tax_components_from_json(self):
        """Extract tax components from JSON field."""
        if not hasattr(self, "tax_components_json") or not self.tax_components_json:
            return {}
            
        try:
            return json.loads(self.tax_components_json)
        except Exception as e:
            logger.error(f"Error parsing tax_components_json: {str(e)}")
            return {}
