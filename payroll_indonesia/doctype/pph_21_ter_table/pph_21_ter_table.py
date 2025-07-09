# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint, fmt_money

from payroll_indonesia.frappe_helpers import logger


class PPh21TERTable(Document):
    def validate(self):
        """Validate TER rate settings."""
        self.income_from = flt(self.income_from)
        self.income_to = flt(self.income_to)
        self.rate = flt(self.rate)
        self.is_highest_bracket = cint(self.is_highest_bracket)

        if not self.status_pajak:
            frappe.throw(_("Kategori TER is required"))

        allowed_ter_categories = ["TER A", "TER B", "TER C"]
        if self.status_pajak not in allowed_ter_categories:
            frappe.throw(
                _("Kategori TER must be one of: {0}").format(", ".join(allowed_ter_categories))
            )

        if self.rate < 0 or self.rate > 100:
            frappe.throw(_("Tax rate must be between 0 and 100 percent"))

        self.validate_range()
        self.validate_duplicate()

        if self.income_to == 0 and not self.is_highest_bracket:
            self.is_highest_bracket = 1
            debug_log(
                f"Setting highest bracket flag for {self.status_pajak} with income_from {self.income_from}",
                "PPh 21 TER Table",
            )

        self.generate_description()

    def validate_range(self):
        """Validate income range."""
        if self.income_from < 0:
            frappe.throw(_("Pendapatan Dari cannot be negative"))

        if self.income_to > 0 and self.income_from >= self.income_to:
            frappe.throw(_("Pendapatan Dari must be less than Pendapatan Hingga"))

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
        ter_explanation = self.get_ter_category_explanation()

        if self.income_from == 0:
            if self.income_to > 0:
                income_range = f"≤ {format_currency_idr(self.income_to)}"
            else:
                income_range = format_currency_idr(self.income_from)
        elif self.income_to == 0 or self.is_highest_bracket:
            income_range = f"> {format_currency_idr(self.income_from)}"
        else:
            income_range = (
                f"{format_currency_idr(self.income_from)}-{format_currency_idr(self.income_to)}"
            )

        self.description = (
            f"{self.status_pajak}: {ter_explanation}, {income_range}, Tarif: {self.rate}%"
        )

    def get_ter_category_explanation(self):
        explanations = {
            "TER A": "PTKP TK/0 (Rp 54 juta/tahun)",
            "TER B": "PTKP K/0, TK/1 (Rp 58,5 juta/tahun)",
            "TER C": "PTKP K/1, TK/2, K/2, TK/3, K/3, dst (Rp 63 juta+/tahun)",
        }
        return explanations.get(self.status_pajak, "")

    def before_save(self):
        if self.income_to == 0:
            self.is_highest_bracket = 1
        if not self.description:
            self.generate_description()


def format_currency_idr(amount):
    try:
        return fmt_money(flt(amount), currency="IDR")
    except Exception:
        try:
            formatted = f"Rp {flt(amount):,.0f}"
            return formatted.replace(",", ".")
        except Exception:
            return f"Rp {amount}"


def setup_ter_rates():
    """
    Setup default TER rates via Payroll Indonesia Settings and ter_rate_table child table.
    Clears existing rows and inserts new ones properly linked.
    """
    try:
        logger.info("Starting TER rate setup via Payroll Indonesia Settings...")

        parent = frappe.get_single("Payroll Indonesia Settings")
        parent.set("ter_rate_table", [])

        default_ter_rates = [
            # status_pajak, income_from, income_to, rate, is_highest_bracket
            ("TER A", 0, 60000000, 5, 0),
            ("TER A", 60000000, 250000000, 15, 0),
            ("TER A", 250000000, 500000000, 25, 0),
            ("TER A", 500000000, 0, 30, 1),
            ("TER B", 0, 60000000, 5, 0),
            ("TER B", 60000000, 250000000, 15, 0),
            ("TER B", 250000000, 500000000, 25, 0),
            ("TER B", 500000000, 0, 30, 1),
            ("TER C", 0, 60000000, 5, 0),
            ("TER C", 60000000, 250000000, 15, 0),
            ("TER C", 250000000, 500000000, 25, 0),
            ("TER C", 500000000, 0, 30, 1),
        ]

        for status_pajak, income_from, income_to, rate, is_highest_bracket in default_ter_rates:
            row = parent.append("ter_rate_table", {})
            row.status_pajak = status_pajak
            row.income_from = income_from
            row.income_to = income_to
            row.rate = rate
            row.is_highest_bracket = is_highest_bracket
            # Description and other fields will be auto-generated on save

        parent.save(ignore_permissions=True)
        frappe.db.commit()

        logger.info("TER rate setup completed successfully via Payroll Indonesia Settings.")
        return True
    except Exception as e:
        logger.error(f"Error during TER rate setup: {str(e)}")
        frappe.log_error(
            f"Error setting up TER rates: {str(e)}\n{frappe.get_traceback()}",
            "TER Rate Setup Error",
        )
        return False


# Optionally, call setup_ter_rates() during installation or migration from hooks or setup
# Example: in setup_module.py or hooks.py, call setup_ter_rates() as needed


# Backwards compatible utility for debugging (if needed)
def debug_log(msg, title=None):
    try:
        logger.debug(f"{title or 'Debug'}: {msg}")
    except Exception:
        pass
