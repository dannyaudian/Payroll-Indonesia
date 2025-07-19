# -*- coding: utf-8 -*-
"""BPJS setup utilities for Payroll Indonesia."""

import frappe

from payroll_indonesia.frappe_helpers import get_logger

logger = get_logger("setup")


def ensure_bpjs_account_mappings(transaction_open: bool = False) -> bool:
    """Ensure each company has a BPJS Account Mapping.

    Args:
        transaction_open: ``True`` if the caller has already opened a database
            transaction. When ``False`` this function will manage its own
            transaction and commit or roll back on failure.

    Returns:
        bool: ``True`` if a mapping was created for at least one company,
        ``False`` otherwise or if an error occurred.
    """

    if not transaction_open:
        frappe.db.begin()

    try:
        from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping import (
            create_default_mapping,
        )

        created = False
        companies = frappe.get_all("Company", pluck="name")
        for company in companies:
            if not frappe.db.exists("BPJS Account Mapping", {"company": company}):
                create_default_mapping(company)
                created = True

        if not transaction_open:
            frappe.db.commit()

        return created
    except Exception as e:
        if not transaction_open:
            frappe.db.rollback()
        logger.error(f"Error ensuring BPJS Account Mappings: {str(e)}")
        return False
