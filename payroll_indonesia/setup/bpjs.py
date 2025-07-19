# -*- coding: utf-8 -*-
"""BPJS setup utilities for Payroll Indonesia."""

import frappe

from payroll_indonesia.frappe_helpers import get_logger

logger = get_logger("setup")


def ensure_bpjs_account_mappings(transaction_open: bool = False) -> bool:
    """Ensure each company has a BPJS Account Mapping."""
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

        return created
    except Exception as e:
        logger.error(f"Error ensuring BPJS Account Mappings: {str(e)}")
        return False
