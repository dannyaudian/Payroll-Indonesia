# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-16 09:39:02 by dannyaudian

import frappe
from frappe import _
import logging

# Set up logger
logger = logging.getLogger(__name__)


def create_bpjs_supplier():
    """
    Create BPJS supplier with correct configuration
    Kept for backward compatibility
    """
    if not frappe.db.exists("Supplier", "BPJS"):
        try:
            supplier = frappe.new_doc("Supplier")
            supplier.supplier_name = "BPJS"
            supplier.supplier_group = "Government"
            supplier.supplier_type = "Government"
            supplier.country = "Indonesia"
            supplier.default_currency = "IDR"

            # Set tax category if exists
            if frappe.db.exists("Tax Category", "Government"):
                supplier.tax_category = "Government"

            supplier.insert()

            frappe.db.commit()

            frappe.msgprint(_("Created default BPJS supplier"))

        except Exception as e:
            logger.error(f"Error creating BPJS supplier: {str(e)}")
            frappe.log_error("Error creating BPJS supplier", str(e))
            frappe.throw(_("Failed to create BPJS supplier: {0}").format(str(e)))


def validate_overlap_period(summary_doc):
    """
    Validate if there's already a BPJS Payment Summary for the same period and company

    Args:
        summary_doc: BPJS Payment Summary document

    Raises:
        frappe.ValidationError: If an overlap is found
    """
    if not summary_doc.month or not summary_doc.year or not summary_doc.company:
        return

    # Convert month to integer if it's a string
    month = summary_doc.month
    if isinstance(month, str):
        try:
            month = int(month)
        except ValueError:
            frappe.throw(_("Month must be a valid number"))

    # Convert year to integer if it's a string
    year = summary_doc.year
    if isinstance(year, str):
        try:
            year = int(year)
        except ValueError:
            frappe.throw(_("Year must be a valid number"))

    # Check for existing documents in the same period
    existing = frappe.db.sql(
        """
        SELECT name, month, year
        FROM `tabBPJS Payment Summary`
        WHERE company = %s
        AND month = %s
        AND year = %s
        AND docstatus < 2
        AND name != %s
    """,
        (summary_doc.company, month, year, summary_doc.name),
        as_dict=1,
    )

    if existing:
        frappe.throw(
            _(
                "A BPJS Payment Summary already exists for period {0}/{1} in company {2}: {3}"
            ).format(month, year, summary_doc.company, existing[0].name)
        )


def validate_component_vs_account(summary_doc):
    """
    Validate that each component has a corresponding account entry

    Args:
        summary_doc: BPJS Payment Summary document

    Returns:
        bool: True if validation passes
    """
    if not hasattr(summary_doc, "komponen") or not summary_doc.komponen:
        return True

    if not hasattr(summary_doc, "account_details") or not summary_doc.account_details:
        frappe.msgprint(
            _("No account details found for components. Please add account details."),
            indicator="orange",
        )
        return False

    # Get all component types from the components table
    component_types = set()
    for comp in summary_doc.komponen:
        if comp.component_type:
            component_types.add(comp.component_type)

    # Get all account types from the account_details table
    account_types = set()
    for acc in summary_doc.account_details:
        if acc.account_type:
            account_types.add(acc.account_type)

    # Check if all component types have corresponding account types
    missing_accounts = component_types - account_types
    if missing_accounts:
        frappe.msgprint(
            _(
                "The following component types do not have corresponding account details: {0}"
            ).format(", ".join(missing_accounts)),
            indicator="orange",
        )
        return False

    # Calculate total amounts from components and account details
    component_total = sum(frappe.utils.flt(comp.amount) for comp in summary_doc.komponen)
    account_total = sum(frappe.utils.flt(acc.amount) for acc in summary_doc.account_details)

    # Check if totals match (with a small tolerance for rounding)
    if abs(component_total - account_total) > 1.0:
        frappe.msgprint(
            _(
                "Component total ({0}) does not match account detail total ({1}). Please reconcile."
            ).format(
                frappe.utils.fmt_money(component_total, currency=frappe.db.get_default("currency")),
                frappe.utils.fmt_money(account_total, currency=frappe.db.get_default("currency")),
            ),
            indicator="orange",
        )
        return False

    return True
