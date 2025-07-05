# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:38:52 by dannyaudian

"""
Controller for Payroll Entry customization for Indonesian payroll.
"""

from typing import Any, Dict

import frappe
from frappe import _
from frappe.utils import getdate
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry

import payroll_indonesia.payroll_indonesia.validations as validations
import payroll_indonesia.override.payroll_entry_functions as pe_functions
from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.frappe_helpers import logger


class CustomPayrollEntry(PayrollEntry):
    """
    Extends standard PayrollEntry with Indonesia-specific functionality.
    All complex tax and BPJS logic is delegated to specialized modules.
    """

    def validate(self) -> None:
        """
        Validate Payroll Entry with Indonesian-specific requirements.
        """
        try:
            # Call parent validation first
            super().validate()

            # Validate December logic
            self._validate_december_logic()

            # Validate employees if applicable
            self._validate_employees()

            # Validate configuration settings
            self._validate_config()

            logger.info(f"Validated Payroll Entry {self.name}")
        except Exception as e:
            logger.exception(f"Error validating Payroll Entry {self.name}: {e}")
            frappe.throw(_("Error validating Payroll Entry: {0}").format(str(e)))

    def _validate_december_logic(self) -> None:
        """
        Validate December logic configuration.
        """
        # Check if December logic is enabled
        is_december = self.get("is_december_run", 0)

        if is_december:
            # Optional warning if not December period
            if hasattr(self, "end_date") and self.end_date:
                end_month = getdate(self.end_date).month
                if end_month != 12:
                    frappe.msgprint(
                        _(
                            "December Progressive Logic is enabled but payroll period "
                            "doesn't end in December. Please verify this is intended."
                        ),
                        indicator="yellow",
                    )

            logger.info(f"Payroll Entry {self.name} using December logic")

    def _validate_employees(self) -> None:
        """
        Validate employee data required for Indonesian payroll.
        """
        # Only proceed if employees are already populated
        if not hasattr(self, "employees") or not self.employees:
            return

        # Get employee IDs
        employee_ids = [e.employee for e in self.employees if e.employee]

        if employee_ids:
            # Validate employee fields
            for emp_id in employee_ids:
                try:
                    validations.validate_employee_fields(emp_id)
                except AttributeError:
                    # Handle missing validation function gracefully
                    logger.warning(
                        f"validate_employee_fields not found in validations module. "
                        f"Skipping validation for {emp_id}"
                    )
                except Exception as e:
                    logger.error(f"Error validating employee {emp_id}: {str(e)}")
                    raise

    def _validate_config(self) -> None:
        """
        Validate configuration settings.
        """
        cfg = get_live_config()

        # Check tax configuration if applicable
        tax_config = cfg.get("tax", {})
        if not tax_config:
            frappe.msgprint(
                _("Tax configuration not found. Using system defaults."), indicator="yellow"
            )

        # Check BPJS configuration if applicable
        bpjs_config = cfg.get("bpjs", {})
        if not bpjs_config:
            frappe.msgprint(
                _("BPJS configuration not found. Using system defaults."), indicator="yellow"
            )

    def on_submit(self) -> None:
        """
        Process Payroll Entry on submission.
        Delegates to payroll_entry_functions.post_submit().
        """
        try:
            # Create salary slips if needed
            if not self._has_salary_slips():
                self.create_salary_slips()

            # Submit salary slips using dedicated function
            result = pe_functions.post_submit(self)

            # Log result
            if result.get("status") == "success":
                logger.info(
                    f"Successfully processed Payroll Entry {self.name}: "
                    f"{result.get('message')}"
                )
            else:
                logger.warning(
                    f"Partially processed Payroll Entry {self.name}: "
                    f"{result.get('message')}"
                )

                # Show message to user
                frappe.msgprint(
                    result.get("message", _("Some issues occurred during processing")),
                    indicator="yellow" if result.get("status") == "partial" else "red",
                )
        except Exception as e:
            logger.exception(f"Error submitting Payroll Entry {self.name}: {e}")
            frappe.throw(_("Error submitting Payroll Entry: {0}").format(str(e)))

    def _has_salary_slips(self) -> bool:
        """
        Check if salary slips have already been created for this Payroll Entry.

        Returns:
            bool: True if salary slips exist
        """
        return bool(
            frappe.db.exists(
                "Salary Slip", {"payroll_entry": self.name, "docstatus": ["in", [0, 1]]}
            )
        )

    def make_payment_entry(self) -> Dict[str, Any]:
        """
        Create payment entry for salary payments.
        Includes employer contributions.

        Returns:
            Dict[str, Any]: Payment entry data
        """
        payment_entry = super().make_payment_entry()

        # Calculate employer contributions
        employer_contributions = pe_functions.calculate_employer_contributions(self)

        # Add employer contribution information if available
        if employer_contributions and payment_entry:
            # Convert to dict if not already
            if not isinstance(payment_entry, dict):
                payment_entry = payment_entry.as_dict()

            # Add employer contribution info
            payment_entry["employer_contributions"] = employer_contributions

            # Add to title/remarks
            payment_entry["user_remark"] = (
                f"{payment_entry.get('user_remark', '')} "
                f"(Including employer contributions: "
                f"{employer_contributions.get('total', 0)})"
            )

        return payment_entry

    def create_salary_slips_from_timesheets(self) -> None:
        """
        Create salary slips for employees with timesheets.
        Delegates to payroll_entry_functions.make_slips_from_timesheets().
        """
        if not getattr(self, "salary_slip_based_on_timesheet", 0):
            frappe.msgprint(_("This payroll is not based on timesheets"))
            return

        created_slips = pe_functions.make_slips_from_timesheets(self)

        if created_slips:
            frappe.msgprint(
                _("Created {0} salary slips from timesheets").format(len(created_slips))
            )
        else:
            frappe.msgprint(
                _(
                    "No salary slips created from timesheets. "
                    "Check if timesheets exist for this period."
                )
            )

    def fill_employee_details(self) -> None:
        """
        Populate employee details with validation.
        """
        # Call parent implementation
        super().fill_employee_details()

        # Additional validation for Indonesian payroll
        self._validate_employees()