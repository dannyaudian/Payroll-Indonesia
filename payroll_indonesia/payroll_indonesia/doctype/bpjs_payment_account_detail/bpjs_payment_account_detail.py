# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa
# For license information, please see license.txt
# Last modified: 2025-06-16 09:24:48 by dannyaudian

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, flt
import logging

# Set up logger
logger = logging.getLogger(__name__)


class BPJSPaymentAccountDetail(Document):
    def validate(self):
        """Validate account detail"""
        # Validate amount must be positive
        if self.amount and self.amount <= 0:
            frappe.throw(_("Amount must be greater than 0"))

        # Validate account type matches the selected account
        self.validate_account_type_match()

        # Update last sync timestamp
        if hasattr(self, "auto_generated") and self.auto_generated:
            self.last_synced = now_datetime()
            self.auto_generated_value = 1

    def validate_account_type_match(self):
        """Validate that the account selected is appropriate for the account type based on Account.account_type"""
        if not self.account or not self.account_type:
            return

        try:
            # Get account details
            account = frappe.get_doc("Account", self.account)
            if not account:
                return

            # Define expected account types for BPJS components
            expected_account_types = {
                "Kesehatan": ["Payable", "Liability"],
                "JHT": ["Payable", "Liability"],
                "JP": ["Payable", "Liability"],
                "JKK": ["Payable", "Liability"],
                "JKM": ["Payable", "Liability"],
            }

            # Get expected account types for this BPJS type
            expected_types = expected_account_types.get(self.account_type, [])

            # Check if account type matches expected types
            if account.account_type not in expected_types and account.root_type != "Liability":
                frappe.log_warning(
                    message=f"Account type mismatch for BPJS {self.account_type}: {account.account_type} (expected {', '.join(expected_types)})",
                    title="BPJS Account Type Mismatch",
                )

                frappe.warning(
                    _(
                        "The selected account '{0}' (type: {1}) may not be appropriate for BPJS {2}. Expected account types: {3}"
                    ).format(
                        account.name,
                        account.account_type,
                        self.account_type,
                        ", ".join(expected_types),
                    ),
                    indicator="orange",
                )
        except Exception as e:
            logger.error(
                f"Error validating account type match: {str(e)}\n"
                f"Account: {self.account}, Type: {self.account_type}"
            )
            frappe.log_error(
                f"Error validating account type match: {str(e)}\n"
                f"Account: {self.account}, Type: {self.account_type}",
                "BPJS Account Detail Validation Error",
            )

    def before_insert(self):
        """Actions before inserting the document"""
        # Generate reference number if empty
        if not self.reference_number:
            # Try to get parent document if this is a child table
            parent_doc = None
            try:
                parent_doc_name = self.get("parent")
                if parent_doc_name:
                    parent_doc = frappe.get_doc(self.get("parenttype"), parent_doc_name)
            except Exception as e:
                logger.error(
                    f"Error retrieving parent document: {str(e)}\n"
                    f"Parent name: {self.get('parent')}, Parent type: {self.get('parenttype')}"
                )

            # Generate format F{year}{month}{rowidx}
            year = ""
            month = ""
            idx = self.idx if hasattr(self, "idx") else frappe.utils.now_datetime().strftime("%S")

            if parent_doc and hasattr(parent_doc, "year") and hasattr(parent_doc, "month"):
                year = str(getattr(parent_doc, "year", ""))
                month = str(getattr(parent_doc, "month", "")).zfill(2)
            else:
                # Use current date
                current_date = frappe.utils.now_datetime()
                year = current_date.strftime("%Y")
                month = current_date.strftime("%m")

            self.reference_number = f"F{year}{month}{idx}"

    def before_save(self):
        """Actions before saving the document"""
        # Automatically set description if empty
        if not self.description and self.account_type:
            self.description = f"BPJS {self.account_type} Payment"

    @staticmethod
    def sync_with_defaults_json(parent_doc=None):
        """
        Sync account details with defaults.json configured accounts

        Args:
            parent_doc (obj, optional): Parent document to update

        Returns:
            int: Number of accounts added
        """
        if not parent_doc or not hasattr(parent_doc, "company") or not parent_doc.company:
            return 0

        try:
            # Get company abbreviation
            company_abbr = frappe.get_cached_value("Company", parent_doc.company, "abbr")
            if not company_abbr:
                return 0

            # Get mapping from defaults.json
            mapping_config = frappe.get_file_json(
                frappe.get_app_path("payroll_indonesia", "config", "defaults.json")
            )
            bpjs_mapping = mapping_config.get("gl_accounts", {}).get("bpjs_account_mapping", {})

            # Map account types to mapping fields
            type_to_field_map = {
                "JHT": "jht_employee_account",
                "JP": "jp_employee_account",
                "Kesehatan": "kesehatan_employee_account",
                "JKK": "jkk_employer_credit_account",
                "JKM": "jkm_employer_credit_account",
            }

            # Calculate totals if parent has employee_details
            bpjs_totals = {"JHT": 0, "JP": 0, "Kesehatan": 0, "JKK": 0, "JKM": 0}

            # Try to calculate totals from employee_details
            if hasattr(parent_doc, "employee_details") and parent_doc.employee_details:
                for emp in parent_doc.employee_details:
                    bpjs_totals["JHT"] += flt(emp.jht_employee) + flt(emp.jht_employer)
                    bpjs_totals["JP"] += flt(emp.jp_employee) + flt(emp.jp_employer)
                    bpjs_totals["Kesehatan"] += flt(emp.kesehatan_employee) + flt(
                        emp.kesehatan_employer
                    )
                    bpjs_totals["JKK"] += flt(emp.jkk)
                    bpjs_totals["JKM"] += flt(emp.jkm)

            # Generate account entries
            accounts_added = 0
            for bpjs_type, mapping_field in type_to_field_map.items():
                # Get account name from mapping
                account_name = bpjs_mapping.get(mapping_field)
                if not account_name:
                    continue

                # Add company abbreviation
                account = f"{account_name} - {company_abbr}"

                # Check if account exists
                if not frappe.db.exists("Account", account):
                    logger.warning(f"Account {account} does not exist for BPJS {bpjs_type}")
                    continue

                # Get amount from totals
                amount = bpjs_totals.get(bpjs_type, 0)
                if amount <= 0:
                    # Skip if no amount
                    continue

                # Generate reference number with format F{year}{month}{idx}
                year = str(getattr(parent_doc, "year", frappe.utils.today()[:4]))
                month = str(getattr(parent_doc, "month", frappe.utils.today()[5:7])).zfill(2)
                idx = accounts_added + 1
                reference_number = f"F{year}{month}{idx}"

                # Add to parent's account_details table
                parent_doc.append(
                    "account_details",
                    {
                        "account_type": bpjs_type,
                        "account": account,
                        "amount": amount,
                        "mapped_from": "defaults.json",
                        "auto_generated": 1,
                        "auto_generated_value": 1,
                        "last_synced": now_datetime(),
                        "description": f"BPJS {bpjs_type} Payment",
                        "reference_number": reference_number,
                    },
                )
                accounts_added += 1

            return accounts_added

        except Exception as e:
            logger.error(f"Error syncing account details with defaults.json: {str(e)}")
            frappe.log_error(
                f"Error syncing account details with defaults.json: {str(e)}\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Account Detail Sync Error",
            )
            return 0
