# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:32:53 by dannyaudian

"""
Salary Slip controller override - koordinator kalkulator Salary Slip.
"""

import logging
from typing import Any, Dict

# from typing import Any, Dict, Optional

import frappe

# from frappe import _

import payroll_indonesia.override.salary_slip.bpjs_calculator as bpjs_calc
import payroll_indonesia.override.salary_slip.tax_calculator as tax_calc
import payroll_indonesia.payroll_indonesia.validations as val

__all__ = ["on_submit", "on_cancel"]

logger = logging.getLogger("payroll_controller")


class PayrollController:
    """
    Controller for Salary Slip document.
    Coordinates calculation modules and handles validation/submission.
    """

    def __init__(self, doc: Any) -> None:
        """Initialize PayrollController with document."""
        self.doc = doc
        self.name = getattr(doc, "name", "New")
        self.doc_type = getattr(doc, "doctype", "Salary Slip")

        logger.info(f"PayrollController initialized for {self.doc_type}: {self.name}")
        self._initialize_fields()

    def _initialize_fields(self) -> None:
        """Initialize additional fields required for Indonesia payroll."""
        if self.doc_type != "Salary Slip":
            return

        defaults = {
            "biaya_jabatan": 0,
            "netto": 0,
            "total_bpjs": 0,
            "is_using_ter": 0,
            "ter_rate": 0,
            "koreksi_pph21": 0,
        }

        for field, default in defaults.items():
            if not hasattr(self.doc, field) or getattr(self.doc, field) is None:
                setattr(self.doc, field, default)

    def _store_bpjs_values(self, components: Dict[str, float]) -> None:
        """Store BPJS component values in the document."""
        if hasattr(self.doc, "total_bpjs"):
            self.doc.total_bpjs = components.get("total_employee", 0)

        # Store individual components if fields exist
        for field in ["kesehatan_employee", "jht_employee", "jp_employee"]:
            if hasattr(self.doc, field):
                setattr(self.doc, field, components.get(field, 0))

    def validate(self) -> None:
        """Validate document based on its type."""
        logger.info(f"Validating {self.doc_type}: {self.name}")

        try:
            if self.doc_type == "BPJS Settings":
                val.validate_bpjs_settings(self.doc)
            elif self.doc_type == "PPh 21 Settings":
                val.validate_pph21_settings(self.doc)
            elif self.doc_type == "Employee":
                val.validate_employee_golongan(self.doc)
            elif self.doc_type == "Salary Slip":
                self._validate_salary_slip()

            logger.info(f"Validation completed for {self.doc_type}: {self.name}")
        except Exception as e:
            logger.error(f"Validation error for {self.doc_type}: {str(e)}")
            raise

    def _validate_salary_slip(self) -> None:
        """Validate Salary Slip and calculate components."""
        bpjs_components = bpjs_calc.calculate_components(self.doc)

        if hasattr(self.doc, "total_bpjs"):
            self.doc.total_bpjs = bpjs_components.get("total_employee", 0)

        # Calculate tax based on method
        self._calculate_tax()

    def _calculate_tax(self) -> None:
        """Calculate tax based on appropriate method."""
        if hasattr(self.doc, "is_december_override") and self.doc.is_december_override:
            tax_calc.calculate_december_pph(self.doc)
        elif hasattr(self.doc, "is_using_ter") and self.doc.is_using_ter:
            tax_calc.calculate_monthly_pph_with_ter(self.doc)
        else:
            tax_calc.calculate_monthly_pph_progressive(self.doc)

    def on_validate(self) -> None:
        """
        Main validation method for Salary Slip.
        Called by Salary Slip hooks during validation.
        """
        try:
            logger.info(f"On validate for Salary Slip: {self.name}")

            # Calculate BPJS components
            bpjs_components = bpjs_calc.calculate_components(self.doc)
            self._store_bpjs_values(bpjs_components)

            # Calculate tax based on method
            self._calculate_tax()

            # Update any dependent fields
            if hasattr(self.doc, "total_deduction"):
                bpjs = getattr(self.doc, "total_bpjs", 0)
                pph21 = getattr(self.doc, "pph21", 0)
                self.doc.total_deduction = self.doc.total_deduction + bpjs + pph21

            logger.info(f"Validation completed for Salary Slip: {self.name}")
        except Exception as e:
            logger.error(f"Validation error: {str(e)}")
            raise

    def on_submit(self) -> None:
        """
        Process document on submission.
        Updates related documents and records.
        """
        try:
            logger.info(f"Processing submission for {self.name}")

            if self.doc_type != "Salary Slip":
                return

            # Validate tax and BPJS calculations one final time
            bpjs_components = bpjs_calc.calculate_components(self.doc)
            self._store_bpjs_values(bpjs_components)
            self._calculate_tax()

            # Update tax records in database
            if hasattr(self.doc, "employee") and self.doc.employee:
                self._update_ytd_records()

            logger.info(f"Submission processing completed for {self.name}")
        except Exception as e:
            logger.error(f"Submission processing error: {str(e)}")
            raise

    def _update_ytd_records(self) -> None:
        """Update Year-to-Date records for employee."""
        employee = getattr(self.doc, "employee", "")

        # Update employee tax summary
        frappe.db.set_value(
            "Employee",
            employee,
            "ytd_pph21",
            frappe.db.get_value("Employee", employee, "ytd_pph21", 0)
            + getattr(self.doc, "pph21", 0),
        )

        # Update employee BPJS summary
        frappe.db.set_value(
            "Employee",
            employee,
            "ytd_bpjs",
            frappe.db.get_value("Employee", employee, "ytd_bpjs", 0)
            + getattr(self.doc, "total_bpjs", 0),
        )

        logger.info(f"Updated YTD records for employee {employee}")


def on_submit(doc, method=None):
    """Salary Slip on_submit hook."""
    PayrollController(doc).on_submit()


def on_cancel(doc, method=None):
    """Salary Slip on_cancel hook."""
    # implement cancellation logic or leave as pass
    pass
