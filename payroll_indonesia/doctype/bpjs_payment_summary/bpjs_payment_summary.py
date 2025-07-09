# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 16:58:59 by dannyaudian

"""
BPJS Payment Summary DocType controller.

This module defines the BPJSPaymentSummary document class and associated service layer
for managing BPJS (social security) payment summaries, including generating journal entries
and payment entries.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union, cast

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_last_day, now_datetime, today

# Import from the core service module instead
from payroll_indonesia.doctype.bpjs_payment_summary.payment_summary_service_core import (
    PaymentSummaryService,
)
from payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_utils import (
    debug_log,
)
from payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_validation import (
    create_bpjs_supplier,
)

# Configure logger
logger = logging.getLogger(__name__)


class BPJSContributionData(TypedDict, total=False):
    """Type definition for BPJS contribution data."""

    jht_employee: float
    jp_employee: float
    kesehatan_employee: float
    jht_employer: float
    jp_employer: float
    kesehatan_employer: float
    jkk: float
    jkm: float


class BPJSPaymentSummary(Document):
    """
    BPJS Payment Summary DocType controller.

    This class handles the management of BPJS payment summaries, including validation,
    calculation of contribution totals, and creation of associated accounting entries.
    """

    def validate(self) -> None:
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

    def set_missing_values(self) -> None:
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
                "Januari",
                "Februari",
                "Maret",
                "April",
                "Mei",
                "Juni",
                "Juli",
                "Agustus",
                "September",
                "Oktober",
                "November",
                "Desember",
            ]

            if 1 <= self.month <= 12:
                # Set month_name if field exists
                if hasattr(self, "month_name"):
                    self.month_name = month_names[self.month - 1]

                # Set month_year_title if field exists
                if hasattr(self, "month_year_title"):
                    self.month_year_title = f"{month_names[self.month - 1]} {self.year}"

    def validate_company(self) -> None:
        """
        Validate company and its default accounts.

        Ensures the company exists and has required default accounts set up.

        Raises:
            frappe.ValidationError: If company is missing or accounts are not properly set.
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

    def validate_month_year(self) -> None:
        """
        Ensure month and year are valid.

        Raises:
            frappe.ValidationError: If month/year values are invalid.
        """
        if not self.month or not self.year:
            frappe.throw(_("Both Month and Year are mandatory"))
        if self.month < 1 or self.month > 12:
            frappe.throw(_("Month must be between 1 and 12"))
        if self.year < 2000:
            frappe.throw(_("Year must be greater than or equal to 2000"))

    def check_and_generate_components(self) -> None:
        """
        Validate BPJS components and auto-generate if needed.

        Creates component entries from employee details or adds default components
        if none exist.
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
            debug_log(f"Added default component for BPJS Payment Summary {self.name}")
        else:
            # Ensure all components have component_type
            for comp in self.komponen:
                if not comp.component_type:
                    comp.component_type = comp.component.replace("BPJS ", "")
                if not comp.amount or comp.amount <= 0:
                    frappe.throw(_("Component amount must be greater than 0"))

    def populate_from_employee_details(self) -> bool:
        """
        Generate komponen entries from employee_details data.

        Returns:
            bool: True if components were successfully generated, False otherwise.
        """
        if not hasattr(self, "employee_details") or not self.employee_details:
            return False

        # Reset existing komponen child table
        self.komponen = []

        # Calculate totals for each BPJS type
        bpjs_totals = {"Kesehatan": 0, "JHT": 0, "JP": 0, "JKK": 0, "JKM": 0}

        # Calculate from employee_details
        for emp in self.employee_details:
            bpjs_totals["Kesehatan"] += flt(emp.kesehatan_employee) + flt(emp.kesehatan_employer)
            bpjs_totals["JHT"] += flt(emp.jht_employee) + flt(emp.jht_employer)
            bpjs_totals["JP"] += flt(emp.jp_employee) + flt(emp.jp_employer)
            bpjs_totals["JKK"] += flt(emp.jkk)
            bpjs_totals["JKM"] += flt(emp.jkm)

        # Map BPJS types to component names
        component_name_map = {
            "Kesehatan": "BPJS Kesehatan",
            "JHT": "BPJS JHT",
            "JP": "BPJS JP",
            "JKK": "BPJS JKK",
            "JKM": "BPJS JKM",
        }

        # Add components
        has_components = False
        for bpjs_type, amount in bpjs_totals.items():
            amount = flt(amount)
            if amount > 0:
                component_name = component_name_map.get(bpjs_type)
                if component_name:
                    self.append(
                        "komponen",
                        {
                            "component": component_name,
                            "component_type": bpjs_type,
                            "amount": amount,
                        },
                    )
                    has_components = True

        # If no valid components, create default component
        if not has_components:
            self.append("komponen", {"component": "BPJS JHT", "component_type": "JHT", "amount": 0})

        return True

    def calculate_total(self) -> None:
        """
        Calculate total from components and set amount field.

        Sums up all component amounts to determine the total payment amount.
        """
        # Validate komponen exists
        if not hasattr(self, "komponen") or not self.komponen:
            self.total = 0
            return

        # Continue with calculation
        self.total = sum(flt(d.amount) for d in self.komponen)

    def validate_total(self) -> None:
        """
        Validate total amount is greater than 0.

        Raises:
            frappe.ValidationError: If total amount is zero or negative.
        """
        if not self.total or self.total <= 0:
            frappe.throw(_("Total amount must be greater than 0"))

    def validate_supplier(self) -> None:
        """
        Validate BPJS supplier exists.

        Creates a default BPJS supplier if one doesn't exist yet.
        """
        if not frappe.db.exists("Supplier", "BPJS"):
            create_bpjs_supplier()

    def set_account_details(self) -> None:
        """
        Set account details from BPJS Settings and Account Mapping.

        Populates account_details child table based on company settings and mappings.

        Raises:
            frappe.ValidationError: If there's an error setting account details.
        """
        if self.docstatus == 1:
            frappe.throw(_("Cannot modify account details after submission"))

        # Get company abbreviation
        company_abbr = getattr(self, "_company_abbr", None) or frappe.get_cached_value(
            "Company", self.company, "abbr"
        )
        self._company_abbr = company_abbr

        # Clear existing account_details
        self.account_details = []

        try:
            service = PaymentSummaryService(self)
            service.set_account_details()
        except Exception as e:
            logger.error(
                f"Error setting account details for BPJS Payment Summary {self.name}: {str(e)}"
            )
            frappe.log_error(
                f"Error setting account details for BPJS Payment Summary {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Account Details Error",
            )
            frappe.throw(_("Error setting account details: {0}").format(str(e)))

    def before_save(self) -> None:
        """
        Ensure all required fields are set before saving.

        Updates last_synced timestamp if applicable.
        """
        # Update last_synced if it exists
        if hasattr(self, "last_synced") and not self.last_synced:
            self.last_synced = now_datetime()

    def on_submit(self) -> None:
        """
        Actions to perform on document submission.

        Sets status to Submitted and creates payment entry.
        """
        self.status = "Submitted"
        self.create_payment_entry()

    def on_cancel(self) -> None:
        """
        Actions to perform on document cancellation.

        Validates linked entries and resets status to Draft.

        Raises:
            frappe.ValidationError: If linked entries are already submitted.
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
    def create_payment_entry(self) -> Dict[str, Any]:
        """
        Create Payment Entry for BPJS Payment Summary.

        Creates a payment entry document to record the payment to BPJS.
        Uses the PaymentSummaryService to ensure idempotency.

        Returns:
            dict: Result with status and payment entry name.

        Raises:
            frappe.ValidationError: If there's an error creating the payment entry.
        """
        try:
            service = PaymentSummaryService(self)
            payment_entry_name = service.create_payment_entry()

            if payment_entry_name:
                result = {
                    "success": True,
                    "payment_entry": payment_entry_name,
                    "message": _("Payment Entry {0} created successfully").format(
                        payment_entry_name
                    ),
                }
            else:
                result = {"success": False, "message": _("No Payment Entry was created")}

            return result
        except Exception as e:
            logger.error(
                f"Error creating Payment Entry for BPJS Payment Summary {self.name}: {str(e)}"
            )
            frappe.log_error(
                f"Error creating Payment Entry for BPJS Payment Summary {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Payment Entry Error",
            )
            return {
                "success": False,
                "message": _("Error creating Payment Entry: {0}").format(str(e)),
            }

    @frappe.whitelist()
    def create_employer_journal(self) -> Dict[str, Any]:
        """
        Create Journal Entry for BPJS employer contributions.

        Creates a journal entry to record the employer's portion of BPJS contributions.
        Uses the PaymentSummaryService to ensure idempotency.

        Returns:
            dict: Result with status and journal entry name.

        Raises:
            frappe.ValidationError: If there's an error creating the journal entry.
        """
        try:
            service = PaymentSummaryService(self)
            journal_entry_name = service.create_employer_journal()

            if journal_entry_name:
                result = {
                    "success": True,
                    "journal_entry": journal_entry_name,
                    "message": _("Journal Entry {0} created successfully").format(
                        journal_entry_name
                    ),
                }
            else:
                result = {"success": False, "message": _("No Journal Entry was created")}

            return result
        except Exception as e:
            logger.error(
                f"Error creating Journal Entry for BPJS Payment Summary {self.name}: {str(e)}"
            )
            frappe.log_error(
                f"Error creating Journal Entry for BPJS Payment Summary {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Journal Entry Error",
            )
            return {
                "success": False,
                "message": _("Error creating Journal Entry: {0}").format(str(e)),
            }

    @frappe.whitelist()
    def get_from_salary_slip(self) -> Dict[str, Any]:
        """
        Get BPJS data from salary slips for the specified period.

        Fetches data from salary slips and populates employee_details.

        Returns:
            dict: Result with status and count.

        Raises:
            frappe.ValidationError: If there's an error fetching data.
        """
        if self.docstatus > 0:
            frappe.throw(_("Cannot fetch data after submission"))

        # Validate required fields
        if not self.company:
            frappe.throw(_("Company is required"))

        if not self.month or not self.year:
            frappe.throw(_("Month and Year are required"))

        try:
            # Clear existing employee details
            self.employee_details = []

            # Get salary slips based on filter
            salary_slips = self._get_filtered_salary_slips()

            if not salary_slips:
                frappe.msgprint(_("No salary slips found for the selected period"))
                return {"success": False, "count": 0}

            # Process each salary slip
            employees_processed = []

            for slip in salary_slips:
                # Skip if employee already processed (to avoid duplicates)
                if slip.employee in employees_processed:
                    continue

                # Extract BPJS data from salary slip
                bpjs_data = self._extract_bpjs_from_salary_slip(slip)

                if bpjs_data:
                    # Add employee to processed list
                    employees_processed.append(slip.employee)

                    # Add to employee_details table
                    self.append(
                        "employee_details",
                        {
                            "employee": slip.employee,
                            "employee_name": slip.employee_name,
                            "salary_slip": slip.name,
                            "jht_employee": bpjs_data.get("jht_employee", 0),
                            "jp_employee": bpjs_data.get("jp_employee", 0),
                            "kesehatan_employee": bpjs_data.get("kesehatan_employee", 0),
                            "jht_employer": bpjs_data.get("jht_employer", 0),
                            "jp_employer": bpjs_data.get("jp_employer", 0),
                            "kesehatan_employer": bpjs_data.get("kesehatan_employer", 0),
                            "jkk": bpjs_data.get("jkk", 0),
                            "jkm": bpjs_data.get("jkm", 0),
                            "last_updated": now_datetime(),
                            "is_synced": 1,
                        },
                    )

            # Regenerate components and account details from employee_details
            if employees_processed:
                self.populate_from_employee_details()
                self.set_account_details()
                self.calculate_total()

                # Set last_synced timestamp
                self.last_synced = now_datetime()

                # Save the document
                self.save()

                return {"success": True, "count": len(employees_processed)}
            else:
                return {"success": False, "count": 0, "message": "No valid BPJS data found"}

        except Exception as e:
            logger.error(f"Error fetching data from salary slips for {self.name}: {str(e)}")
            frappe.log_error(
                f"Error fetching data from salary slips for {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Salary Slip Fetch Error",
            )
            frappe.throw(_("Error fetching data from salary slips: {0}").format(str(e)))

    def _get_filtered_salary_slips(self) -> List[Dict[str, Any]]:
        """
        Get salary slips based on filter criteria.

        Returns:
            list: List of salary slip documents matching the filter criteria.
        """
        filters = {"docstatus": 1, "company": self.company}

        # Convert month and year to integers
        month = int(self.month) if isinstance(self.month, str) else self.month
        year = int(self.year) if isinstance(self.year, str) else self.year

        # Add date-based filters
        if hasattr(self, "salary_slip_filter") and self.salary_slip_filter:
            if self.salary_slip_filter == "Periode Saat Ini":
                # Get slips for current month and year
                filters.update(
                    {
                        "start_date": [
                            "between",
                            [f"{year}-{month:02d}-01", get_last_day(f"{year}-{month:02d}-01")],
                        ]
                    }
                )
            elif self.salary_slip_filter == "Periode Kustom":
                # Custom period - use custom fields if available or default to month range
                if (
                    hasattr(self, "from_date")
                    and hasattr(self, "to_date")
                    and self.from_date
                    and self.to_date
                ):
                    filters.update(
                        {"start_date": [">=", self.from_date], "end_date": ["<=", self.to_date]}
                    )
                else:
                    # Default to current month
                    filters.update(
                        {
                            "start_date": [
                                "between",
                                [f"{year}-{month:02d}-01", get_last_day(f"{year}-{month:02d}-01")],
                            ]
                        }
                    )
            elif self.salary_slip_filter == "Semua Slip Belum Terbayar":
                # Get all slips not linked to a BPJS payment
                # This is more complex, so instead of filtering, we'll get all slips
                # and filter later in code
                pass
        else:
            # Default to current month
            filters.update(
                {
                    "start_date": [
                        "between",
                        [f"{year}-{month:02d}-01", get_last_day(f"{year}-{month:02d}-01")],
                    ]
                }
            )

        # Get salary slips based on filters
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters=filters,
            fields=["name", "employee", "employee_name", "start_date", "end_date"],
        )

        # For "Semua Slip Belum Terbayar" filter, filter out slips already linked
        # to other BPJS payments
        if (
            hasattr(self, "salary_slip_filter")
            and self.salary_slip_filter == "Semua Slip Belum Terbayar"
        ):
            # Get list of salary slips already linked to BPJS payments
            linked_slips = frappe.get_all(
                "BPJS Payment Summary Detail",
                filters={"docstatus": 1, "salary_slip": ["is", "set"]},
                fields=["salary_slip"],
            )
            linked_slip_names = [slip.salary_slip for slip in linked_slips if slip.salary_slip]

            # Filter out already linked slips
            salary_slips = [slip for slip in salary_slips if slip.name not in linked_slip_names]

        return salary_slips

    def _extract_bpjs_from_salary_slip(
        self, slip: Dict[str, Any]
    ) -> Optional[BPJSContributionData]:
        """
        Extract BPJS data from a salary slip.

        Args:
            slip: Salary slip document or dict

        Returns:
            dict: BPJS contribution data or None if no data found
        """
        # Get the full salary slip document
        doc = frappe.get_doc("Salary Slip", slip.name)

        bpjs_data: BPJSContributionData = {
            "jht_employee": 0,
            "jp_employee": 0,
            "kesehatan_employee": 0,
            "jht_employer": 0,
            "jp_employer": 0,
            "kesehatan_employer": 0,
            "jkk": 0,
            "jkm": 0,
        }

        # Extract employee contributions from deductions
        if hasattr(doc, "deductions") and doc.deductions:
            for d in doc.deductions:
                if "BPJS Kesehatan" in d.salary_component and "Employee" not in d.salary_component:
                    bpjs_data["kesehatan_employee"] += flt(d.amount)
                elif "BPJS JHT" in d.salary_component and "Employee" not in d.salary_component:
                    bpjs_data["jht_employee"] += flt(d.amount)
                elif "BPJS JP" in d.salary_component and "Employee" not in d.salary_component:
                    bpjs_data["jp_employee"] += flt(d.amount)
                # Support alternative naming with "Employee" suffix
                elif "BPJS Kesehatan Employee" in d.salary_component:
                    bpjs_data["kesehatan_employee"] += flt(d.amount)
                elif "BPJS JHT Employee" in d.salary_component:
                    bpjs_data["jht_employee"] += flt(d.amount)
                elif "BPJS JP Employee" in d.salary_component:
                    bpjs_data["jp_employee"] += flt(d.amount)

        # Extract employer contributions from earnings or statistical components
        if hasattr(doc, "earnings") and doc.earnings:
            for e in doc.earnings:
                if "BPJS Kesehatan Employer" in e.salary_component:
                    bpjs_data["kesehatan_employer"] += flt(e.amount)
                elif "BPJS JHT Employer" in e.salary_component:
                    bpjs_data["jht_employer"] += flt(e.amount)
                elif "BPJS JP Employer" in e.salary_component:
                    bpjs_data["jp_employer"] += flt(e.amount)
                elif "BPJS JKK" in e.salary_component:
                    bpjs_data["jkk"] += flt(e.amount)
                elif "BPJS JKM" in e.salary_component:
                    bpjs_data["jkm"] += flt(e.amount)

        # Check if we found any BPJS data
        has_data = any(flt(value) > 0 for value in bpjs_data.values())
        return bpjs_data if has_data else None

    @frappe.whitelist()
    def sync_from_employees(self) -> Dict[str, Any]:
        """
        Fetch BPJS data from employee records.

        Updates employee_details with active employees' BPJS information.

        Returns:
            dict: Result with status and count.

        Raises:
            frappe.ValidationError: If there's an error fetching data.
        """
        if self.docstatus > 0:
            frappe.throw(_("Cannot fetch data after submission"))

        try:
            # Clear existing employee details
            self.employee_details = []

            # Get active employees
            employees = frappe.get_all(
                "Employee",
                filters={"status": "Active", "company": self.company},
                fields=["name", "employee_name", "bpjs_tk_no", "bpjs_kes_no"],
            )

            if not employees:
                frappe.msgprint(_("No active employees found"))
                return {"success": False, "count": 0}

            employees_processed = []

            for emp in employees:
                # Skip if employee has no BPJS numbers
                if not emp.get("bpjs_tk_no") and not emp.get("bpjs_kes_no"):
                    continue

                # Get employee salary structure assignment
                salary_structure = frappe.get_all(
                    "Salary Structure Assignment",
                    filters={"employee": emp.name, "docstatus": 1},
                    fields=["base", "salary_structure"],
                    order_by="from_date desc",
                    limit=1,
                )

                if not salary_structure:
                    continue

                # Calculate BPJS contributions based on base salary
                base_salary = salary_structure[0].get("base", 0)
                bpjs_data = self._calculate_bpjs_from_base(base_salary)

                if bpjs_data:
                    # Add employee to processed list
                    employees_processed.append(emp.name)

                    # Add to employee_details table
                    self.append(
                        "employee_details",
                        {
                            "employee": emp.name,
                            "employee_name": emp.employee_name,
                            "salary_slip": None,
                            "jht_employee": bpjs_data.get("jht_employee", 0),
                            "jp_employee": bpjs_data.get("jp_employee", 0),
                            "kesehatan_employee": bpjs_data.get("kesehatan_employee", 0),
                            "jht_employer": bpjs_data.get("jht_employer", 0),
                            "jp_employer": bpjs_data.get("jp_employer", 0),
                            "kesehatan_employer": bpjs_data.get("kesehatan_employer", 0),
                            "jkk": bpjs_data.get("jkk", 0),
                            "jkm": bpjs_data.get("jkm", 0),
                            "last_updated": now_datetime(),
                            "is_synced": 1,
                        },
                    )

            # Regenerate components and account details from employee_details
            if employees_processed:
                self.populate_from_employee_details()
                self.set_account_details()
                self.calculate_total()

                # Set last_synced timestamp
                self.last_synced = now_datetime()

                # Save the document
                self.save()

                return {"success": True, "count": len(employees_processed)}
            else:
                return {"success": False, "count": 0, "message": "No valid BPJS data found"}

        except Exception as e:
            logger.error(f"Error fetching data from employees for {self.name}: {str(e)}")
            frappe.log_error(
                f"Error fetching data from employees for {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Employee Fetch Error",
            )
            frappe.throw(_("Error fetching data from employees: {0}").format(str(e)))

    def _calculate_bpjs_from_base(self, base_salary: float) -> Optional[BPJSContributionData]:
        """
        Calculate BPJS contributions based on base salary.

        Args:
            base_salary: Base salary amount

        Returns:
            dict: BPJS contribution data or None if no data could be calculated
        """
        if not base_salary or base_salary <= 0:
            return None

        # Get BPJS settings
        bpjs_settings = frappe.get_cached_value(
            "BPJS Settings",
            {"company": self.company},
            [
                "jht_employee_percent",
                "jht_employer_percent",
                "jp_employee_percent",
                "jp_employer_percent",
                "kesehatan_employee_percent",
                "kesehatan_employer_percent",
                "jkk_percent",
                "jkm_percent",
            ],
            as_dict=1,
        )

        if not bpjs_settings:
            # Use default percentages if settings not found
            bpjs_settings = {
                "jht_employee_percent": 2,
                "jht_employer_percent": 3.7,
                "jp_employee_percent": 1,
                "jp_employer_percent": 2,
                "kesehatan_employee_percent": 1,
                "kesehatan_employer_percent": 4,
                "jkk_percent": 0.24,
                "jkm_percent": 0.3,
            }

        # Calculate contributions based on percentages
        bpjs_data: BPJSContributionData = {
            "jht_employee": flt(
                base_salary * flt(bpjs_settings.get("jht_employee_percent", 0)) / 100
            ),
            "jp_employee": flt(
                base_salary * flt(bpjs_settings.get("jp_employee_percent", 0)) / 100
            ),
            "kesehatan_employee": flt(
                base_salary * flt(bpjs_settings.get("kesehatan_employee_percent", 0)) / 100
            ),
            "jht_employer": flt(
                base_salary * flt(bpjs_settings.get("jht_employer_percent", 0)) / 100
            ),
            "jp_employer": flt(
                base_salary * flt(bpjs_settings.get("jp_employer_percent", 0)) / 100
            ),
            "kesehatan_employer": flt(
                base_salary * flt(bpjs_settings.get("kesehatan_employer_percent", 0)) / 100
            ),
            "jkk": flt(base_salary * flt(bpjs_settings.get("jkk_percent", 0)) / 100),
            "jkm": flt(base_salary * flt(bpjs_settings.get("jkm_percent", 0)) / 100),
        }

        return bpjs_data

    @frappe.whitelist()
    def get_accounts_mapping(self) -> Dict[str, Any]:
        """
        Get account mappings for BPJS components.

        Fetches account mappings from BPJS Settings or creates default mappings.

        Returns:
            dict: Account mappings for each BPJS component.
        """
        try:
            # Get account mappings from BPJS Settings
            mapping = frappe.get_all(
                "BPJS Account Mapping",
                filters={"parent": ["like", f"%{self.company}%"]},
                fields=["component_type", "account", "cost_center"],
                order_by="component_type",
            )

            if not mapping:
                # Create default mappings
                company_abbr = getattr(self, "_company_abbr", None) or frappe.get_cached_value(
                    "Company", self.company, "abbr"
                )

                default_mapping = {
                    "JHT": f"BPJS JHT - {company_abbr}",
                    "JP": f"BPJS JP - {company_abbr}",
                    "Kesehatan": f"BPJS Kesehatan - {company_abbr}",
                    "JKK": f"BPJS JKK - {company_abbr}",
                    "JKM": f"BPJS JKM - {company_abbr}",
                }

                # Check if accounts exist, if not create them
                accounts_created = []
                for component, account_name in default_mapping.items():
                    if not frappe.db.exists("Account", account_name):
                        frappe.msgprint(
                            _("Account {0} does not exist. Please create it first.").format(
                                account_name
                            )
                        )
                    else:
                        accounts_created.append(
                            {
                                "component_type": component,
                                "account": account_name,
                                "cost_center": None,
                            }
                        )

                return {"success": True, "mapping": accounts_created}
            else:
                return {"success": True, "mapping": mapping}

        except Exception as e:
            logger.error(f"Error getting account mappings for {self.name}: {str(e)}")
            frappe.log_error(
                f"Error getting account mappings for {self.name}: {str(e)}\n\n"
                f"Traceback: {frappe.get_traceback()}",
                "BPJS Account Mapping Error",
            )
            return {"success": False, "message": str(e)}

    @frappe.whitelist()
    def get_payment_status(self) -> Dict[str, Any]:
        """
        Get payment status of the BPJS payment summary.

        Returns:
            dict: Payment status information.
        """
        result = {"success": True}

        # Check payment entry status
        if self.payment_entry:
            pe_status = frappe.db.get_value(
                "Payment Entry",
                self.payment_entry,
                ["docstatus", "status", "reference_no", "reference_date"],
            )

            if pe_status:
                result.update(
                    {
                        "payment_entry_status": {
                            "docstatus": pe_status[0],
                            "status": pe_status[1],
                            "reference_no": pe_status[2],
                            "reference_date": pe_status[3],
                        }
                    }
                )

        # Check journal entry status
        if self.journal_entry:
            je_status = frappe.db.get_value(
                "Journal Entry", self.journal_entry, ["docstatus", "user_remark", "posting_date"]
            )

            if je_status:
                result.update(
                    {
                        "journal_entry_status": {
                            "docstatus": je_status[0],
                            "remarks": je_status[1],
                            "posting_date": je_status[2],
                        }
                    }
                )

        return result


def validate_bpjs_payment_summary(doc, method=None):
    """
    Hook function to validate BPJS Payment Summary.

    Args:
        doc: The document being validated
        method: The method that triggered this hook
    """
    # Additional validations if needed
    pass
