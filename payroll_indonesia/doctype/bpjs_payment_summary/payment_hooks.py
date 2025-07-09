# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 16:03:46 by dannyaudian

"""
Payment Entry hooks for BPJS Payment Summary integration.

This module contains hooks that handle Payment Entry lifecycle events
and integrate them with the BPJS Payment Summary workflow.
"""

import logging
from typing import Any, Optional

import frappe
from frappe import _

from .bpjs_payment_service import PaymentSummaryService

logger = logging.getLogger(__name__)


def on_payment_entry_submit(payment_entry: Any, method: Optional[str] = None) -> None:
    """
    Hook triggered when Payment Entry is submitted.

    If the Payment Entry is linked to a BPJS Payment Summary, this hook will
    automatically create an employer contribution journal entry.

    Args:
        payment_entry: The Payment Entry document
        method: Hook method name (unused, kept for API compatibility)
    """
    # Skip if in migration or installation
    if getattr(frappe.flags, "in_migrate", False) or getattr(frappe.flags, "in_install", False):
        return

    # Check if payment entry has references to BPJS Payment Summary
    if not hasattr(payment_entry, "references") or not payment_entry.references:
        return

    bpjs_references = []
    for ref in payment_entry.references:
        if (
            hasattr(ref, "reference_doctype")
            and ref.reference_doctype == "BPJS Payment Summary"
            and hasattr(ref, "reference_name")
            and ref.reference_name
        ):
            bpjs_references.append(ref.reference_name)

    # Process each BPJS Payment Summary
    for summary_name in bpjs_references:
        try:
            # Check if BPJS Payment Summary exists and is submitted
            if not frappe.db.exists("BPJS Payment Summary", summary_name):
                continue

            summary_status = frappe.db.get_value("BPJS Payment Summary", summary_name, "docstatus")
            if summary_status != 1:  # Not submitted
                continue

            # Create service and trigger journal entry creation
            service = PaymentSummaryService(summary_name)
            journal_entry = service.create_employer_journal()

            if journal_entry:
                logger.info(
                    f"Created Journal Entry {journal_entry} for BPJS Payment "
                    f"Summary {summary_name} after Payment Entry {payment_entry.name} submission"
                )

                # Update payment entry with reference to journal entry
                payment_entry.db_set(
                    "remarks",
                    f"{payment_entry.remarks or ''}\nEmployer Journal: {journal_entry}",
                    update_modified=False,
                )

        except Exception as e:
            logger.error(
                f"Error creating employer journal for BPJS Payment Summary {summary_name}: "
                f"{str(e)}"
            )
            frappe.log_error(
                f"Error creating employer journal for BPJS Payment Summary {summary_name} "
                f"from Payment Entry {payment_entry.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Employer Journal Creation Error",
            )
