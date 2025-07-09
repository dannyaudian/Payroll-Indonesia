# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 15:57:28 by dannyaudian

"""
Validation module for BPJS Payment Summary.

This module provides validation functions for BPJS Payment Summary
and related data, ensuring business rules are enforced.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple, Union, cast

import frappe
from frappe import _
from frappe.utils import flt, cint, get_last_day

logger = logging.getLogger(__name__)


class BPJSPaymentValidator:
    """
    Central validator for BPJS payment-related operations.

    This class contains static methods for validating BPJS Payment Summary documents,
    detail records, and account configurations.
    """

    @staticmethod
    def validate_summary(doc: Any) -> None:
        """
        Validate a BPJS Payment Summary document.

        Args:
            doc: BPJS Payment Summary document

        Raises:
            frappe.ValidationError: If validation fails
        """
        # Skip if in migration or installation
        if getattr(frappe.flags, "in_migrate", False) or getattr(frappe.flags, "in_install", False):
            return

        # Skip if table doesn't exist yet
        if not frappe.db.table_exists("BPJS Payment Summary"):
            return

        # Validate required fields
        BPJSPaymentValidator._validate_required_fields(doc)

        # Validate month and year format
        BPJSPaymentValidator._validate_month_year_format(doc)

        # Validate period overlap
        BPJSPaymentValidator._validate_overlap_period(doc)

        # Validate components vs accounts
        BPJSPaymentValidator._validate_component_vs_account(doc)

        # Validate totals
        BPJSPaymentValidator._validate_totals(doc)

        # Ensure BPJS supplier exists
        if not frappe.db.exists("Supplier", "BPJS"):
            BPJSPaymentValidator._create_bpjs_supplier()

    @staticmethod
    def validate_detail(child: Any) -> None:
        """
        Validate a BPJS Payment Summary Detail record.

        Args:
            child: BPJS Payment Summary Detail document

        Raises:
            frappe.ValidationError: If validation fails
        """
        # Skip if in migration or installation
        if getattr(frappe.flags, "in_migrate", False) or getattr(frappe.flags, "in_install", False):
            return

        # Skip if table doesn't exist yet
        if not frappe.db.table_exists("BPJS Payment Summary Detail"):
            return

        # Validate amount is positive
        if hasattr(child, "amount") and child.amount is not None:
            if flt(child.amount) <= 0:
                frappe.throw(_("Amount must be greater than 0"))

        # Validate employee information
        if hasattr(child, "employee") and not child.employee:
            frappe.throw(_("Employee is required for BPJS payment detail"))

        # Validate contribution amounts
        BPJSPaymentValidator._validate_contribution_amounts(child)

    @staticmethod
    def validate_accounts(company: str) -> None:
        """
        Validate BPJS-related accounts for a company.

        Args:
            company: Company name

        Raises:
            frappe.ValidationError: If validation fails
        """
        # Skip if in migration or installation
        if getattr(frappe.flags, "in_migrate", False) or getattr(frappe.flags, "in_install", False):
            return

        # Skip if tables don't exist yet
        if not frappe.db.table_exists("Company") or not frappe.db.table_exists("Account"):
            return

        # Check company exists
        if not frappe.db.exists("Company", company):
            frappe.throw(_("Company {0} does not exist").format(company))

        # Validate required accounts
        BPJSPaymentValidator._validate_required_accounts(company)

    @staticmethod
    def _validate_required_fields(doc: Any) -> None:
        """
        Validate that required fields are provided.

        Args:
            doc: BPJS Payment Summary document

        Raises:
            frappe.ValidationError: If required fields are missing
        """
        if not hasattr(doc, "company") or not doc.company:
            frappe.throw(_("Company is required"))

        if not hasattr(doc, "month") or doc.month is None:
            frappe.throw(_("Month is required"))

        if not hasattr(doc, "year") or doc.year is None:
            frappe.throw(_("Year is required"))

        if not hasattr(doc, "posting_date") or not doc.posting_date:
            frappe.throw(_("Posting date is required"))

    @staticmethod
    def _validate_month_year_format(doc: Any) -> None:
        """
        Validate month and year format.

        Args:
            doc: BPJS Payment Summary document

        Raises:
            frappe.ValidationError: If month or year is invalid
        """
        # Validate month
        try:
            month = int(doc.month) if isinstance(doc.month, str) else doc.month
            if month < 1 or month > 12:
                frappe.throw(_("Month must be between 1 and 12"))
        except (ValueError, TypeError):
            frappe.throw(_("Month must be a valid number"))

        # Validate year
        try:
            year = int(doc.year) if isinstance(doc.year, str) else doc.year
            if year < 2000 or year > 2100:  # Reasonable range check
                frappe.throw(_("Year must be between 2000 and 2100"))
        except (ValueError, TypeError):
            frappe.throw(_("Year must be a valid number"))

    @staticmethod
    def _validate_overlap_period(doc: Any) -> None:
        """
        Validate if there's already a BPJS Payment Summary for the same period and company.

        Args:
            doc: BPJS Payment Summary document

        Raises:
            frappe.ValidationError: If an overlap is found
        """
        if not doc.month or not doc.year or not doc.company:
            return

        # Convert month to integer if it's a string
        month = doc.month
        if isinstance(month, str):
            try:
                month = int(month)
            except ValueError:
                return  # This will be caught by _validate_month_year_format

        # Convert year to integer if it's a string
        year = doc.year
        if isinstance(year, str):
            try:
                year = int(year)
            except ValueError:
                return  # This will be caught by _validate_month_year_format

        # Check for existing documents in the same period
        existing = frappe.db.get_all(
            "BPJS Payment Summary",
            filters={
                "company": doc.company,
                "month": month,
                "year": year,
                "docstatus": ["<", 2],
                "name": ["!=", doc.name],
            },
            fields=["name"],
        )

        if existing:
            frappe.throw(
                _(
                    "A BPJS Payment Summary already exists for period {0}/{1} in company {2}: {3}"
                ).format(month, year, doc.company, existing[0].name)
            )

    @staticmethod
    def _validate_component_vs_account(doc: Any) -> None:
        """
        Validate that each component has a corresponding account entry.

        Args:
            doc: BPJS Payment Summary document

        Raises:
            frappe.ValidationError: If components and accounts don't match
        """
        if not hasattr(doc, "komponen") or not doc.komponen:
            return

        if not hasattr(doc, "account_details") or not doc.account_details:
            frappe.throw(_("No account details found for components. Please add account details."))

        # Get all component types from the components table
        component_types = set()
        for comp in doc.komponen:
            if hasattr(comp, "component_type") and comp.component_type:
                component_types.add(comp.component_type)

        # Get all account types from the account_details table
        account_types = set()
        for acc in doc.account_details:
            if hasattr(acc, "account_type") and acc.account_type:
                account_types.add(acc.account_type)

        # Check if all component types have corresponding account types
        missing_accounts = component_types - account_types
        if missing_accounts:
            frappe.throw(
                _(
                    "The following component types do not have corresponding account details: {0}"
                ).format(", ".join(missing_accounts))
            )

        # Calculate total amounts from components and account details
        component_total = sum(flt(comp.amount) for comp in doc.komponen)
        account_total = sum(flt(acc.amount) for acc in doc.account_details)

        # Check if totals match (with a small tolerance for rounding)
        if abs(component_total - account_total) > 1.0:
            frappe.throw(
                _(
                    "Component total ({0}) does not match account detail total ({1}). "
                    "Please reconcile."
                ).format(
                    frappe.utils.fmt_money(component_total), frappe.utils.fmt_money(account_total)
                )
            )

    @staticmethod
    def _validate_totals(doc: Any) -> None:
        """
        Validate calculation totals in the document.

        Args:
            doc: BPJS Payment Summary document

        Raises:
            frappe.ValidationError: If totals are inconsistent
        """
        if not hasattr(doc, "total") or doc.total is None:
            return

        # If komponen child table exists, validate total against it
        if hasattr(doc, "komponen") and doc.komponen:
            calculated_total = sum(flt(comp.amount) for comp in doc.komponen)
            if abs(flt(doc.total) - calculated_total) > 0.1:  # Small tolerance for rounding
                frappe.throw(
                    _("Document total ({0}) does not match calculated total ({1})").format(
                        frappe.utils.fmt_money(doc.total), frappe.utils.fmt_money(calculated_total)
                    )
                )

        # Check total is positive
        if flt(doc.total) <= 0:
            frappe.throw(_("Total amount must be greater than 0"))

    @staticmethod
    def _validate_contribution_amounts(child: Any) -> None:
        """
        Validate contribution amounts in detail records.

        Args:
            child: BPJS Payment Summary Detail document

        Raises:
            frappe.ValidationError: If contribution amounts are invalid
        """
        # Check if any contribution amount is negative
        contribution_fields = [
            "kesehatan_employee",
            "kesehatan_employer",
            "jht_employee",
            "jht_employer",
            "jp_employee",
            "jp_employer",
            "jkk",
            "jkm",
        ]

        for field in contribution_fields:
            if hasattr(child, field) and child.get(field) is not None:
                if flt(child.get(field)) < 0:
                    frappe.throw(_("{0} cannot be negative").format(frappe.unscrub(field)))

        # Verify total matches the sum of contributions
        if hasattr(child, "amount"):
            total = sum(flt(getattr(child, field, 0)) for field in contribution_fields)
            if abs(flt(child.amount) - total) > 0.1:  # Small tolerance for rounding
                child.amount = total

    @staticmethod
    def _validate_required_accounts(company: str) -> None:
        """
        Validate that required accounts exist for BPJS processing.

        Args:
            company: Company name

        Raises:
            frappe.ValidationError: If required accounts are missing
        """
        company_abbr = frappe.get_cached_value("Company", company, "abbr")

        # Required accounts
        required_accounts = {
            "default_payable_account": _("Default Payable Account"),
            "default_expense_account": _("Default Expense Account"),
            "default_bank_account": _("Default Bank Account"),
            "cost_center": _("Cost Center"),
        }

        # Check company default accounts
        missing_accounts = []
        for account_field, account_label in required_accounts.items():
            account = frappe.get_cached_value("Company", company, account_field)
            if not account:
                missing_accounts.append(account_label)

        if missing_accounts:
            frappe.throw(
                _("Missing required accounts for company {0}: {1}").format(
                    company, ", ".join(missing_accounts)
                )
            )

        # Check BPJS-specific accounts
        bpjs_accounts = [
            f"BPJS Kesehatan Payable - {company_abbr}",
            f"BPJS JHT Payable - {company_abbr}",
            f"BPJS JP Payable - {company_abbr}",
        ]

        existing_accounts = frappe.db.get_all(
            "Account", filters={"name": ["in", bpjs_accounts]}, pluck="name"
        )

        if len(existing_accounts) < len(bpjs_accounts):
            # We don't throw here, just log a warning
            logger.warning(
                f"Some BPJS accounts are missing for company {company}. "
                "They will be created automatically when needed."
            )

    @staticmethod
    def _create_bpjs_supplier() -> None:
        """
        Create BPJS supplier with correct configuration.

        Raises:
            frappe.ValidationError: If supplier creation fails
        """
        try:
            # Skip if Supplier table doesn't exist
            if not frappe.db.table_exists("Supplier"):
                return

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

            logger.info("Created default BPJS supplier")

        except Exception as e:
            logger.error(f"Error creating BPJS supplier: {str(e)}")
            frappe.log_error(
                f"Error creating BPJS supplier: {str(e)}\n{frappe.get_traceback()}",
                "BPJS Supplier Creation Error",
            )
            frappe.throw(_("Failed to create BPJS supplier: {0}").format(str(e)))


# Legacy function kept for backward compatibility
def create_bpjs_supplier() -> None:
    """
    Create BPJS supplier with correct configuration.
    Legacy function kept for backward compatibility.

    Raises:
        frappe.ValidationError: If supplier creation fails
    """
    BPJSPaymentValidator._create_bpjs_supplier()
