# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-03 04:16:21 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint, fmt_money

# Import utility functions
from payroll_indonesia.payroll_indonesia.utils import debug_log


class PPh21TERTable(Document):
    def validate(self):
        """Validate TER rate settings."""
        # Ensure fields are converted to proper types
        self.income_from = flt(self.income_from)
        self.income_to = flt(self.income_to)
        self.rate = flt(self.rate)
        self.is_highest_bracket = cint(self.is_highest_bracket)

        # Validate required fields
        if not self.status_pajak:
            frappe.throw(_("Kategori TER is required"))

        # Validate status_pajak value is among allowed options
        allowed_ter_categories = ["TER A", "TER B", "TER C"]
        if self.status_pajak not in allowed_ter_categories:
            frappe.throw(
                _("Kategori TER must be one of: {0}").format(", ".join(allowed_ter_categories))
            )

        # Validate rate is within acceptable range
        if self.rate < 0 or self.rate > 100:
            frappe.throw(_("Tax rate must be between 0 and 100 percent"))

        # Validate income range
        self.validate_range()

        # Check for duplicates
        self.validate_duplicate()

        # Set highest bracket flag if appropriate
        if self.income_to == 0 and not self.is_highest_bracket:
            self.is_highest_bracket = 1
            debug_log(
                f"Setting highest bracket flag for {self.status_pajak} with income_from {self.income_from}",
                "PPh 21 TER Table",
            )

        # Generate description
        self.generate_description()

    def validate_range(self):
        """Validate income range."""
        if self.income_from < 0:
            frappe.throw(_("Pendapatan Dari cannot be negative"))

        if self.income_to > 0 and self.income_from >= self.income_to:
            frappe.throw(_("Pendapatan Dari must be less than Pendapatan Hingga"))

        # For highest bracket, income_to should be 0
        if self.income_to == 0 and not self.is_highest_bracket:
            self.is_highest_bracket = 1
        elif self.is_highest_bracket and self.income_to > 0:
            self.income_to = 0
            debug_log(
                f"Set income_to to 0 for highest bracket for {self.status_pajak}",
                "PPh 21 TER Table",
            )

    def validate_duplicate(self):
        """Check for duplicate status+range combinations."""
        if not self.is_new():
            # Only check for duplicates when creating new records
            return

        exists = frappe.db.exists(
            "PPh 21 TER Table",
            {
                "name": ["!=", self.name],
                "status_pajak": self.status_pajak,
                "income_from": self.income_from,
                "income_to": self.income_to,
            },
        )

        if exists:
            frappe.throw(
                _("Duplicate TER rate exists for category {0} with range {1} to {2}").format(
                    self.status_pajak,
                    format_currency_idr(self.income_from),
                    format_currency_idr(self.income_to) if self.income_to > 0 else "∞",
                )
            )

    def generate_description(self):
        """Set the description automatically with proper formatting."""
        # Get TER category explanation
        ter_explanation = self.get_ter_category_explanation()

        # Generate the income range part of the description
        if self.income_from == 0:
            # Starting from 0
            if self.income_to > 0:
                income_range = f"≤ {format_currency_idr(self.income_to)}"
            else:
                # This shouldn't happen (income_from=0, income_to=0)
                income_range = format_currency_idr(self.income_from)
        elif self.income_to == 0 or self.is_highest_bracket:
            # Highest bracket
            income_range = f"> {format_currency_idr(self.income_from)}"
        else:
            # Regular range
            income_range = (
                f"{format_currency_idr(self.income_from)}-{format_currency_idr(self.income_to)}"
            )

        # Set the description
        self.description = (
            f"{self.status_pajak}: {ter_explanation}, {income_range}, Tarif: {self.rate}%"
        )

    def get_ter_category_explanation(self):
        """Get explanation for TER category."""
        explanations = {
            "TER A": "PTKP TK/0 (Rp 54 juta/tahun)",
            "TER B": "PTKP K/0, TK/1 (Rp 58,5 juta/tahun)",
            "TER C": "PTKP K/1, TK/2, K/2, TK/3, K/3, dst (Rp 63 juta+/tahun)",
        }
        return explanations.get(self.status_pajak, "")

    def before_save(self):
        """
        Final validations and setups before saving.
        """
        # Ensure is_highest_bracket is set correctly
        if self.income_to == 0:
            self.is_highest_bracket = 1

        # Ensure description is generated
        if not self.description:
            self.generate_description()


def format_currency_idr(amount):
    """
    Format amount as Indonesian Rupiah with proper thousand separators.

    Args:
        amount: The amount to format

    Returns:
        str: Formatted amount as Rupiah
    """
    try:
        # Use fmt_money to format the currency with proper IDR formatting
        return fmt_money(flt(amount), currency="IDR")
    except Exception:
        # Fallback to simple formatting if fmt_money fails
        try:
            # Format with thousand separator
            formatted = f"Rp {flt(amount):,.0f}"
            # Replace commas with dots for Indonesian formatting
            return formatted.replace(",", ".")
        except Exception:
            return f"Rp {amount}"
