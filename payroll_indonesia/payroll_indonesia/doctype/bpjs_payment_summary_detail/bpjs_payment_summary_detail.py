# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 15:47:01 by dannyaudian

"""
BPJS Payment Summary Detail DocType controller.

This module defines the BPJSPaymentSummaryDetail document class.
It serves as a passive data holder for BPJS contribution details
with minimal logic delegated to the parent service.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

# Set up logger
logger = logging.getLogger(__name__)


class BPJSPaymentSummaryDetail(Document):
    """
    Child table for storing BPJS Payment Summary details.

    A passive data holder for BPJS contribution details per employee,
    with validation and update hooks that trigger parent document recalculations.
    """

    def validate(self) -> None:
        """
        Validate payment details.

        Ensures positive amount values and basic data integrity.
        """
        # Basic validation only - complex logic moved to parent service
        if self.amount and self.amount <= 0:
            frappe.throw(_("Amount must be greater than 0"))

    def after_insert(self) -> None:
        """
        Hook triggered after inserting a new detail record.

        Calls parent service to recalculate totals.
        """
        self._trigger_parent_recalculation()

    def on_update(self) -> None:
        """
        Hook triggered after updating a detail record.

        Calls parent service to recalculate totals.
        """
        original_creation = frappe.db.get_value(self.doctype, self.name, "creation")
        self._trigger_parent_recalculation()
        if original_creation and self.creation != original_creation:
            logger.warning(
                f"Creation timestamp mismatch for {self.name}. Resetting to original value"
            )
            self.creation = original_creation

    def _trigger_parent_recalculation(self) -> None:
        """
        Trigger recalculation of totals in parent document.

        Skips recalculation during migrations to prevent issues.
        """
        # Skip if Frappe is in installation/migration mode
        if getattr(frappe.flags, "in_migrate", False) or getattr(frappe.flags, "in_install", False):
            return

        # Skip if parent table doesn't exist yet
        if not frappe.db.exists("DocType", "BPJS Payment Summary") or not frappe.db.table_exists(
            "BPJS Payment Summary"
        ):
            return

        if self.parent and frappe.db.exists("BPJS Payment Summary", self.parent):
            try:
                # Import here to avoid circular imports
                from ..bpjs_payment_summary.bpjs_payment_service import PaymentSummaryService

                # Get parent document
                parent_doc = frappe.get_doc("BPJS Payment Summary", self.parent)

                # Create service and trigger recalculation
                service = PaymentSummaryService(parent_doc)
                service.recompute_totals()

            except ImportError:
                logger.warning(
                    f"Could not import PaymentSummaryService for recalculation: {self.parent}"
                )
            except Exception as e:
                logger.error(f"Error triggering recalculation for {self.parent}: {str(e)}")


def bulk_sync(slips: List[Union[str, Dict[str, Any], Document]]) -> List[Dict[str, Any]]:
    """
    Bulk sync data from multiple salary slips.

    Args:
        slips: List of salary slip names or objects

    Returns:
        list: List of dictionaries with BPJS data from each slip
    """
    # Skip if tables don't exist
    if not frappe.db.table_exists("Salary Slip") or not frappe.db.table_exists("Salary Detail"):
        logger.warning("Required tables don't exist, skipping bulk sync")
        return []

    if not slips:
        return []

    # Extract slip names if objects are provided
    slip_names = []
    for slip in slips:
        if isinstance(slip, str):
            slip_names.append(slip)
        elif isinstance(slip, dict) and "name" in slip:
            slip_names.append(slip["name"])
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

        if not slips_data:
            return []

        # Get all salary details for these slips in one query
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

        # Process the data using utility function
        from ..bpjs_payment_summary.bpjs_payment_utils import extract_bpjs_data_from_components

        result = []
        for slip in slips_data:
            # Get components for this slip
            slip_deductions = [d for d in deductions if d.parent == slip.name]
            slip_earnings = [e for e in earnings if e.parent == slip.name]

            # Extract BPJS data
            bpjs_data = extract_bpjs_data_from_components(
                slip.employee, slip.employee_name, slip.name, slip_deductions, slip_earnings
            )

            # Only include if there's any BPJS data
            if bpjs_data and bpjs_data.get("amount", 0) > 0:
                result.append(bpjs_data)

        return result

    except Exception as e:
        logger.error(f"Error in bulk sync: {str(e)}")
        frappe.log_error(
            f"Error in BPJSPaymentSummaryDetail.bulk_sync: {str(e)}\n"
            f"Traceback: {frappe.get_traceback()}",
            "BPJS Payment Summary Detail Error",
        )
        return []
