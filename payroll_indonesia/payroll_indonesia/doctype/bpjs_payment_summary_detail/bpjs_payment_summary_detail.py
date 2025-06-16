# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-16 09:40:37 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime
import logging

# Set up logger
logger = logging.getLogger(__name__)


class BPJSPaymentSummaryDetail(Document):
    def validate(self):
        """Validate payment details"""
        if self.amount and self.amount <= 0:
            frappe.throw(_("Amount must be greater than 0"))

        # Auto-calculate total amount if not set
        if not self.amount:
            self.calculate_total_amount()

    def calculate_total_amount(self):
        """Calculate the total amount from all BPJS components"""
        total = (
            flt(self.kesehatan_employee)
            + flt(self.jht_employee)
            + flt(self.jp_employee)
            + flt(self.kesehatan_employer)
            + flt(self.jht_employer)
            + flt(self.jp_employer)
            + flt(self.jkk)
            + flt(self.jkm)
        )

        self.amount = total if total > 0 else 0

    @classmethod
    def bulk_sync(cls, slips):
        """
        Bulk sync data from multiple salary slips

        Args:
            slips (list): List of salary slip names or objects

        Returns:
            list: List of dictionaries with BPJS data from each slip
        """
        if not slips:
            return []

        # Extract slip names if objects are provided
        slip_names = []
        for slip in slips:
            if isinstance(slip, str):
                slip_names.append(slip)
            elif hasattr(slip, "name"):
                slip_names.append(slip.name)

        if not slip_names:
            return []

        try:
            # Fetch all slips and their components in a single query
            slips_data = frappe.get_all(
                "Salary Slip",
                filters={"name": ["in", slip_names], "docstatus": 1},
                fields=["name", "employee", "employee_name"],
            )

            # Get all salary details for these slips in one query
            if slips_data:
                # Get all deductions
                deductions = frappe.get_all(
                    "Salary Detail",
                    filters={
                        "parent": ["in", slip_names],
                        "parentfield": "deductions",
                        "salary_component": ["like", "%BPJS%"],
                    },
                    fields=["parent", "salary_component", "amount"],
                )

                # Get all earnings
                earnings = frappe.get_all(
                    "Salary Detail",
                    filters={
                        "parent": ["in", slip_names],
                        "parentfield": "earnings",
                        "salary_component": ["like", "%BPJS%"],
                    },
                    fields=["parent", "salary_component", "amount"],
                )

                # Process the data
                result = []
                for slip in slips_data:
                    bpjs_data = {
                        "employee": slip.employee,
                        "employee_name": slip.employee_name,
                        "salary_slip": slip.name,
                        "jht_employee": 0,
                        "jp_employee": 0,
                        "kesehatan_employee": 0,
                        "jht_employer": 0,
                        "jp_employer": 0,
                        "kesehatan_employer": 0,
                        "jkk": 0,
                        "jkm": 0,
                        "last_updated": now_datetime(),
                        "is_synced": 1,
                    }

                    # Process deductions (employee contributions)
                    for deduction in deductions:
                        if deduction.parent != slip.name:
                            continue

                        component = deduction.salary_component.lower()

                        if "kesehatan" in component and "employee" in component:
                            bpjs_data["kesehatan_employee"] += flt(deduction.amount)
                        elif "jht" in component and "employee" in component:
                            bpjs_data["jht_employee"] += flt(deduction.amount)
                        elif "jp" in component and "employee" in component:
                            bpjs_data["jp_employee"] += flt(deduction.amount)
                        # Handle cases without "employee" in name
                        elif "kesehatan" in component and "employer" not in component:
                            bpjs_data["kesehatan_employee"] += flt(deduction.amount)
                        elif "jht" in component and "employer" not in component:
                            bpjs_data["jht_employee"] += flt(deduction.amount)
                        elif "jp" in component and "employer" not in component:
                            bpjs_data["jp_employee"] += flt(deduction.amount)

                    # Process earnings (employer contributions)
                    for earning in earnings:
                        if earning.parent != slip.name:
                            continue

                        component = earning.salary_component.lower()

                        if "kesehatan" in component and "employer" in component:
                            bpjs_data["kesehatan_employer"] += flt(earning.amount)
                        elif "jht" in component and "employer" in component:
                            bpjs_data["jht_employer"] += flt(earning.amount)
                        elif "jp" in component and "employer" in component:
                            bpjs_data["jp_employer"] += flt(earning.amount)
                        elif "jkk" in component:
                            bpjs_data["jkk"] += flt(earning.amount)
                        elif "jkm" in component:
                            bpjs_data["jkm"] += flt(earning.amount)

                    # Calculate total amount
                    bpjs_data["amount"] = (
                        flt(bpjs_data["kesehatan_employee"])
                        + flt(bpjs_data["jht_employee"])
                        + flt(bpjs_data["jp_employee"])
                        + flt(bpjs_data["kesehatan_employer"])
                        + flt(bpjs_data["jht_employer"])
                        + flt(bpjs_data["jp_employer"])
                        + flt(bpjs_data["jkk"])
                        + flt(bpjs_data["jkm"])
                    )

                    # Only include if there's any BPJS data
                    if bpjs_data["amount"] > 0:
                        result.append(bpjs_data)

                return result

            return []

        except Exception as e:
            logger.error(f"Error in bulk sync: {str(e)}")
            frappe.log_error(
                f"Error in BPJSPaymentSummaryDetail.bulk_sync: {str(e)}\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Payment Summary Detail Error",
            )
            return []
