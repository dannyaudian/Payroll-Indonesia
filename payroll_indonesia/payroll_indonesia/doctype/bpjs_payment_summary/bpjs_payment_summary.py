# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
"""
BPJS Payment Summary DocType controller.

This module defines the BPJSPaymentSummary document class and handles basic validations.
Business logic is delegated to the payment_summary_service_core module.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_last_day, now_datetime, today

from payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.payment_summary_service_core import (
    PaymentSummaryService,
    create_payment_entry,
    fetch_salary_slip_data,
)
class BPJSPaymentSummary(Document):
    """
    BPJS Payment Summary DocType controller.

    This class handles the management of BPJS payment summaries, including validation,
    calculation of contribution totals, and creation of associated accounting entries.
    """

    def validate(self):
        """
        Validate document before save/submit.

        Performs all validation checks and sets default values where needed.
        """
        # Ensure month and year are integers
        if self.month and isinstance(self.month, str):
            try:
                self.month = int(self.month)
            except (ValueError, TypeError):
                frappe.throw(_("Month must be a valid number"))

        if self.year and isinstance(self.year, str):
            try:
                self.year = int(self.year)
            except (ValueError, TypeError):
                frappe.throw(_("Year must be a valid number"))

        self.set_missing_values()
        self.validate_company()
        self.validate_month_year()
        self.check_and_generate_components()
        self.calculate_total()
        self.validate_total()
        self.validate_supplier()
        self.set_account_details()

    def set_missing_values(self):
        """
        Set default values for required fields.

        Populates empty fields with appropriate default values.
        """
        # Set posting_date if empty
        if not self.posting_date:
            self.posting_date = today()

        # Set month name and title if fields exist
        if hasattr(self, "month") and hasattr(self, "year") and self.month and self.year:
            month_names = [
                "Januari", "Februari", "Maret", "April", "Mei", "Juni",
                "Juli", "Agustus", "September", "Oktober", "November", "Desember",
            ]

            if 1 <= self.month <= 12:
                # Set month_name if field exists
                if hasattr(self, "month_name"):
                    self.month_name = month_names[self.month - 1]

                # Set month_year_title if field exists
                if hasattr(self, "month_year_title"):
                    self.month_year_title = f"{month_names[self.month - 1]} {self.year}"

    def validate_company(self):
        """
        Validate company and its default accounts.

        Ensures the company exists and has required default accounts set up.
        """
        if not self.company:
            frappe.throw(_("Company is mandatory"))

        # Check default accounts
        company_doc = frappe.get_doc("Company", self.company)
        if not company_doc.default_bank_account:
            frappe.throw(_("Default Bank Account not set for Company {0}").format(self.company))
        if not company_doc.default_payable_account:
            frappe.throw(_("Default Payable Account not set for Company {0}").format(self.company))

        # Store company abbreviation for later use
        self._company_abbr = frappe.get_cached_value("Company", self.company, "abbr")

    def validate_month_year(self):
        """
        Ensure month and year are valid.
        """
        if not self.month or not self.year:
            frappe.throw(_("Both Month and Year are mandatory"))
        if self.month < 1 or self.month > 12:
            frappe.throw(_("Month must be between 1 and 12"))
        if self.year < 2000:
            frappe.throw(_("Year must be greater than or equal to 2000"))

    def check_and_generate_components(self):
        """
        Validate BPJS components and auto-generate if needed.
        """
        # If components are empty but employee_details exist, auto-generate components
        if (
            (not self.komponen or len(self.komponen) == 0)
            and hasattr(self, "employee_details")
            and self.employee_details
        ):
            self.populate_from_employee_details()

        # If still empty, add default component
        if not self.komponen or len(self.komponen) == 0:
            self.append(
                "komponen",
                {
                    "component": "BPJS JHT",
                    "component_type": "JHT",
                    "amount": flt(self.amount) if hasattr(self, "amount") and self.amount else 0,
                },
            )
        else:
            # Ensure all components have component_type
            for comp in self.komponen:
                if not comp.component_type:
                    comp.component_type = comp.component.replace("BPJS ", "")
                if not comp.amount or comp.amount <= 0:
                    frappe.throw(_("Component amount must be greater than 0"))

    def populate_from_employee_details(self):
        """
        Generate komponen entries from employee_details data.

        Returns:
            bool: True if components were successfully generated, False otherwise.
        """
            service = PaymentSummaryService(self)
        return service.populate_from_employee_details()

    def calculate_total(self):
        """
        Calculate total from components and set amount field.
        """
        # Validate komponen exists
        if not hasattr(self, "komponen") or not self.komponen:
            self.total = 0
            return

        # Continue with calculation
        self.total = sum(flt(d.amount) for d in self.komponen)

    def validate_total(self):
        """
        Validate total amount is greater than 0.
        """
        if not self.total or self.total <= 0:
            frappe.throw(_("Total amount must be greater than 0"))

    def validate_supplier(self):
        """
        Validate BPJS supplier exists.
        """
        if not frappe.db.exists("Supplier", "BPJS"):
            self.create_bpjs_supplier()

    def create_bpjs_supplier(self):
        """Create BPJS supplier if it doesn't exist."""
        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = "BPJS"
        supplier.supplier_group = "Services"
        supplier.supplier_type = "Company"
        supplier.country = "Indonesia"
        supplier.insert()
        return supplier.name

    def set_account_details(self):
        """
        Set account details from BPJS Settings and Account Mapping.
        """
        if self.docstatus == 1:
            frappe.throw(_("Cannot modify account details after submission"))
            service = PaymentSummaryService(self)
        service.set_account_details()

    def before_save(self):
        """
        Ensure all required fields are set before saving.
        """
        # Update last_synced if it exists
        if hasattr(self, "last_synced") and not self.last_synced:
            self.last_synced = now_datetime()

    def on_submit(self):
        """
        Actions to perform on document submission.
        """
        self.status = "Submitted"

    def on_cancel(self):
        """
        Actions to perform on document cancellation.
        """
        if self.payment_entry:
            pe_status = frappe.db.get_value("Payment Entry", self.payment_entry, "docstatus")
            if pe_status and int(pe_status) == 1:
                frappe.throw(_("Cannot cancel document with submitted Payment Entry"))
        if self.journal_entry:
            je_status = frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus")
            if je_status and int(je_status) == 1:
                frappe.throw(
                    _(
                        "Cannot cancel document with submitted Journal Entry. "
                        "Cancel the Journal Entry first."
                    )
                )

        self.status = "Draft"

    @frappe.whitelist()
    def generate_payment_entry(self):
        """
        Create Payment Entry for BPJS Payment Summary.

        Returns:
            dict: Result with status and payment entry name.
        """
        try:
            payment_entry_name = create_payment_entry(self)

            if payment_entry_name:
                result = {
                    "success": True,
                    "message": _("Payment Entry {0} created successfully").format(
                        payment_entry_name
                    ),
                    "name": payment_entry_name
                }
            else:
                result = {"success": False, "message": _("No Payment Entry was created")}

            return result
        except Exception as e:
            frappe.log_error(
                f"Error creating Payment Entry for BPJS Payment Summary {self.name}: {str(e)}",
                "BPJS Payment Entry Error",
            )
            return {
                "success": False,
                "message": _("Error creating Payment Entry: {0}").format(str(e)),
            }

    @frappe.whitelist()
    def create_employer_journal(self):
        """
        Create Journal Entry for BPJS employer contributions.

        Returns:
            dict: Result with status and journal entry name.
        """
        service = PaymentSummaryService(self)
        return service.create_employer_journal()

    @frappe.whitelist()
    def get_from_salary_slip(self):
        """
        Get BPJS data from salary slips for the specified period.

        Returns:
            dict: Result with status and count.
        """
        try:
            return fetch_salary_slip_data(self)
        except Exception as e:
            frappe.log_error(
                f"Error fetching data from salary slips for {self.name}: {str(e)}",
                "BPJS Salary Slip Fetch Error",
            )
            frappe.throw(_("Error fetching data from salary slips: {0}").format(str(e)))

    @frappe.whitelist()
    def get_accounts_mapping(self):
        """
        Get account mappings for BPJS components.
        """
        service = PaymentSummaryService(self)
        return service.get_accounts_mapping()

    @frappe.whitelist()
    def get_payment_status(self):
        """
        Get payment status of the BPJS payment summary.
        """
        service = PaymentSummaryService(self)
        return service.get_payment_status()
