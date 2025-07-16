# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 16:58:59 by dannyaudian

"""
BPJS Payment Summary Service Core.

This module provides the core PaymentSummaryService class for handling
BPJS Payment Summary operations. It's designed to avoid circular imports
by centralizing core functionality needed by multiple modules.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union, cast

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, today, now_datetime
from payroll_indonesia.utilities import sanitize_update_data

from payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_utils import (
    safe_decimal,
    format_reference,
    get_month_name,
    calculate_period_dates,
    PayableLine,
    ExpenseLine,
    collect_payable_lines,
    compute_employer_expense,
    get_payment_accounts,
    debug_log,
)

logger = logging.getLogger(__name__)


class PaymentSummaryService:
    """
    Service class for BPJS Payment Summary operations.

    This class provides core business logic for creating and managing BPJS Payment Summaries,
    creating payment entries, and managing journal entries.
    """

    def __init__(self, doc_or_name: Union[str, Any]) -> None:
        """
        Initialize the service with a document or document name.

        Args:
            doc_or_name: BPJS Payment Summary document or name
        """
        if isinstance(doc_or_name, str):
            self.doc = frappe.get_doc("BPJS Payment Summary", doc_or_name)
        else:
            self.doc = doc_or_name

        # Cache company abbreviation for later use
        self.company_abbr = frappe.get_cached_value("Company", self.doc.company, "abbr")

    def set_account_details(self) -> None:
        """
        Set account details from BPJS Account Mapping.

        Populates account_details child table based on components and mapping settings.

        Raises:
            frappe.ValidationError: If there's an error setting account details.
        """
        if not hasattr(self.doc, "account_details"):
            frappe.throw(_("Account details table not found in document"))

        # Clear existing account_details
        self.doc.account_details = []

        # Get BPJS account mapping for this company
        mapping = self._get_bpjs_account_mapping()

        # Get month and year for reference numbers
        month = cint(self.doc.month)
        year = cint(self.doc.year)

        # Get BPJS type totals from components
        bpjs_totals = self._calculate_bpjs_type_totals()

        # Add account details for each BPJS type with amount > 0
        for bpjs_type, amount in bpjs_totals.items():
            if flt(amount) <= 0:
                continue

            # Get account from mapping
            account = self._get_account_for_bpjs_type(bpjs_type, mapping)

            if account:
                # Format reference number
                reference = format_reference(bpjs_type, month, year)

                # Add to account_details
                self.doc.append(
                    "account_details",
                    {
                        "account_type": bpjs_type,
                        "account": account,
                        "amount": flt(amount),
                        "description": f"BPJS {bpjs_type} Payment for {get_month_name(month)} {year}",
                        "reference_number": reference,
                    },
                )

    def recompute_totals(self) -> float:
        """
        Recompute totals from components and update the document.

        Returns:
            float: Updated total amount
        """
        # Ensure document has komponen table
        if not hasattr(self.doc, "komponen"):
            return 0.0

        # Sum up all component amounts
        total = sum(flt(row.amount) for row in self.doc.komponen)

        # Update document total
        self.doc.total = total

        # Commit changes to database if this is a saved document
        if self.doc.name and not self.doc.is_new():
            data = sanitize_update_data({"total": total})
            if "total" in data:
                self.doc.db_set("total", total, update_modified=False)

        return total

    def create_payment_entry(self) -> Optional[str]:
        """
        Create a Payment Entry for BPJS Payment Summary.

        Returns:
            str: Payment Entry name if created, None otherwise

        Raises:
            frappe.ValidationError: If there's an error creating payment entry.
        """
        # Validate document is submitted
        if self.doc.docstatus != 1:
            frappe.throw(_("Document must be submitted before creating payment entry"))

        # Check if payment entry already exists
        if self.doc.payment_entry:
            payment_entry = frappe.db.exists("Payment Entry", self.doc.payment_entry)
            if payment_entry:
                return payment_entry

        try:
            # Get default accounts
            company_doc = frappe.get_doc("Company", self.doc.company)
            default_bank = company_doc.default_bank_account

            if not default_bank:
                frappe.throw(
                    _("Default Bank Account not set for company {0}").format(self.doc.company)
                )

            # Get month and year for reference
            month = cint(self.doc.month)
            year = cint(self.doc.year)
            month_name = get_month_name(month)

            # Create new payment entry
            payment_entry = frappe.new_doc("Payment Entry")
            payment_entry.payment_type = "Pay"
            payment_entry.mode_of_payment = "Bank"  # Default mode
            payment_entry.paid_from = default_bank
            payment_entry.company = self.doc.company
            payment_entry.posting_date = self.doc.posting_date
            payment_entry.party_type = "Supplier"
            payment_entry.party = "BPJS"  # Default BPJS supplier
            payment_entry.reference_no = f"BPJS-{month:02d}-{year}"
            payment_entry.reference_date = self.doc.posting_date

            # Set payment amount
            payment_entry.paid_amount = flt(self.doc.total)
            payment_entry.received_amount = flt(self.doc.total)

            # Set remarks
            payment_entry.remarks = f"BPJS Payment for {month_name} {year}"

            # Add references to account details if we have any
            if hasattr(self.doc, "account_details") and self.doc.account_details:
                for account_detail in self.doc.account_details:
                    payment_entry.append(
                        "references",
                        {
                            "reference_doctype": "BPJS Payment Summary",
                            "reference_name": self.doc.name,
                            "allocated_amount": flt(account_detail.amount),
                        },
                    )
            else:
                # Add a single reference to the payment summary
                payment_entry.append(
                    "references",
                    {
                        "reference_doctype": "BPJS Payment Summary",
                        "reference_name": self.doc.name,
                        "allocated_amount": flt(self.doc.total),
                    },
                )

            # Save and submit payment entry
            payment_entry.insert()

            # Update BPJS Payment Summary with payment entry reference
            self.doc.payment_entry = payment_entry.name
            self.doc.status = "Paid"

            # Update database directly
            if not self.doc.is_new():
                data = sanitize_update_data(
                    {"payment_entry": payment_entry.name, "status": "Paid"}
                )
                if "payment_entry" in data:
                    self.doc.db_set("payment_entry", payment_entry.name)
                if "status" in data:
                    self.doc.db_set("status", "Paid")

            debug_log(f"Created Payment Entry {payment_entry.name} for {self.doc.name}")
            return payment_entry.name

        except Exception as e:
            logger.error(f"Error creating payment entry for {self.doc.name}: {str(e)}")
            frappe.log_error(
                f"Error creating payment entry for {self.doc.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Payment Entry Error",
            )
            frappe.throw(_("Error creating payment entry: {0}").format(str(e)))
            return None

    def create_employer_journal(self) -> Optional[str]:
        """
        Create a Journal Entry for employer BPJS contributions.

        Returns:
            str: Journal Entry name if created, None otherwise

        Raises:
            frappe.ValidationError: If there's an error creating journal entry.
        """
        # Validate document is submitted
        if self.doc.docstatus != 1:
            frappe.throw(_("Document must be submitted before creating journal entry"))

        # Check if journal entry already exists
        if self.doc.journal_entry:
            journal_entry = frappe.db.exists("Journal Entry", self.doc.journal_entry)
            if journal_entry:
                return journal_entry

        try:
            # Get default cost center
            cost_center = frappe.db.get_value("Company", self.doc.company, "cost_center")

            if not cost_center:
                frappe.throw(
                    _("Default Cost Center not set for company {0}").format(self.doc.company)
                )

            # Compute employer expenses
            def get_accounts_for_component(component_type: str) -> Tuple[str, str]:
                """Get payment and expense accounts for a component type."""
                # Build settings dict with expected account names
                settings = self._get_bpjs_account_settings()
                return get_payment_accounts(lambda: settings, self.doc.company, component_type)

            expense_lines = compute_employer_expense(
                self.doc, cost_center, get_accounts_for_component
            )

            # Skip if no expenses to record
            if not expense_lines:
                debug_log(f"No employer expenses to record for {self.doc.name}")
                return None

            # Get month and year for reference
            month = cint(self.doc.month)
            year = cint(self.doc.year)
            month_name = get_month_name(month)

            # Create new journal entry
            journal_entry = frappe.new_doc("Journal Entry")
            journal_entry.voucher_type = "Journal Entry"
            journal_entry.company = self.doc.company
            journal_entry.posting_date = self.doc.posting_date
            journal_entry.user_remark = f"BPJS Employer Contribution for {month_name} {year}"

            # Add expense lines
            for expense in expense_lines:
                journal_entry.append(
                    "accounts",
                    {
                        "account": expense.account,
                        "debit_in_account_currency": flt(expense.amount),
                        "credit_in_account_currency": 0,
                        "cost_center": expense.cost_center,
                        "reference_type": "BPJS Payment Summary",
                        "reference_name": self.doc.name,
                    },
                )

            # Add payable lines (crediting the expense)
            employer_total = sum(flt(expense.amount) for expense in expense_lines)

            # Use default payable account
            default_payable = frappe.db.get_value(
                "Company", self.doc.company, "default_payable_account"
            )

            journal_entry.append(
                "accounts",
                {
                    "account": default_payable,
                    "debit_in_account_currency": 0,
                    "credit_in_account_currency": flt(employer_total),
                    "cost_center": cost_center,
                    "party_type": "Supplier",
                    "party": "BPJS",
                    "reference_type": "BPJS Payment Summary",
                    "reference_name": self.doc.name,
                },
            )

            # Save journal entry
            journal_entry.insert()

            # Update BPJS Payment Summary with journal entry reference
            self.doc.journal_entry = journal_entry.name

            # Update database directly
            if not self.doc.is_new():
                data = sanitize_update_data({"journal_entry": journal_entry.name})
                if "journal_entry" in data:
                    self.doc.db_set("journal_entry", journal_entry.name)

            debug_log(f"Created Journal Entry {journal_entry.name} for {self.doc.name}")
            return journal_entry.name

        except Exception as e:
            logger.error(f"Error creating journal entry for {self.doc.name}: {str(e)}")
            frappe.log_error(
                f"Error creating journal entry for {self.doc.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Journal Entry Error",
            )
            frappe.throw(_("Error creating journal entry: {0}").format(str(e)))
            return None

    def _get_bpjs_account_mapping(self) -> Dict[str, Any]:
        """
        Get BPJS account mapping for the company.

        Returns:
            Dict[str, Any]: Account mapping dict or empty dict if not found
        """
        mapping = frappe.get_all(
            "BPJS Account Mapping", filters={"company": self.doc.company}, fields=["*"], limit=1
        )

        if mapping:
            return mapping[0]

        # Return empty dict if no mapping found
        return {}

    def _get_bpjs_account_settings(self) -> Dict[str, Any]:
        """
        Get BPJS account settings.

        Returns:
            Dict[str, Any]: Account settings dict
        """
        # Try to get BPJS Settings first
        settings: Dict[str, Any] = {}

        try:
            bpjs_settings = frappe.get_doc("BPJS Settings")

            # Map fields to expected account names
            for field in dir(bpjs_settings):
                if field.endswith("_account") and not field.startswith("_"):
                    settings[field] = bpjs_settings.get(field)
        except Exception:
            # If BPJS Settings not found, use default account names
            pass

        # Ensure default accounts if missing
        required_accounts = [
            "payment_account",
            "expense_account",
            "kesehatan_account",
            "kesehatan_expense_account",
            "jht_account",
            "jht_expense_account",
            "jp_account",
            "jp_expense_account",
            "jkk_account",
            "jkk_expense_account",
            "jkm_account",
            "jkm_expense_account",
        ]

        for account in required_accounts:
            if account not in settings or not settings[account]:
                # Generate default account name based on type
                if account.endswith("_expense_account"):
                    settings[account] = f"BPJS Expense - {self.company_abbr}"
                else:
                    settings[account] = f"BPJS Payable - {self.company_abbr}"

        return settings

    def _get_account_for_bpjs_type(self, bpjs_type: str, mapping: Dict[str, Any]) -> Optional[str]:
        """
        Get account for a specific BPJS type from mapping.

        Args:
            bpjs_type: BPJS type (e.g., Kesehatan, JHT)
            mapping: Account mapping dict

        Returns:
            Optional[str]: Account name or None if not found
        """
        # Try to find account in mapping
        account_field_map = {
            "Kesehatan": "bpjs_kesehatan_payable_account",
            "JHT": "bpjs_ketenagakerjaan_jht_payable_account",
            "JP": "bpjs_ketenagakerjaan_jp_payable_account",
            "JKK": "bpjs_ketenagakerjaan_jkk_payable_account",
            "JKM": "bpjs_ketenagakerjaan_jkm_payable_account",
        }

        # Try specific account first
        field_name = account_field_map.get(bpjs_type)
        if field_name and field_name in mapping and mapping[field_name]:
            return mapping[field_name]

        # Try general payable accounts
        if bpjs_type in ["JHT", "JP", "JKK", "JKM"]:
            if (
                "bpjs_ketenagakerjaan_payable_account" in mapping
                and mapping["bpjs_ketenagakerjaan_payable_account"]
            ):
                return mapping["bpjs_ketenagakerjaan_payable_account"]

        # Fall back to default payable account
        default_payable = frappe.db.get_value(
            "Company", self.doc.company, "default_payable_account"
        )

        return default_payable

    def _calculate_bpjs_type_totals(self) -> Dict[str, float]:
        """
        Calculate totals for each BPJS type from components.

        Returns:
            Dict[str, float]: BPJS type totals
        """
        bpjs_totals: Dict[str, float] = {"Kesehatan": 0, "JHT": 0, "JP": 0, "JKK": 0, "JKM": 0}

        # Calculate from components
        for comp in self.doc.komponen:
            if comp.component_type:
                bpjs_type = comp.component_type
                if bpjs_type in bpjs_totals:
                    bpjs_totals[bpjs_type] += flt(comp.amount)
            else:
                # Try to determine type from component name
                component_name = comp.component.lower()
                if "kesehatan" in component_name:
                    bpjs_totals["Kesehatan"] += flt(comp.amount)
                elif "jht" in component_name:
                    bpjs_totals["JHT"] += flt(comp.amount)
                elif "jp" in component_name:
                    bpjs_totals["JP"] += flt(comp.amount)
                elif "jkk" in component_name:
                    bpjs_totals["JKK"] += flt(comp.amount)
                elif "jkm" in component_name:
                    bpjs_totals["JKM"] += flt(comp.amount)

        return bpjs_totals
