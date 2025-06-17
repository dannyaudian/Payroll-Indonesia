# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-23 05:15:32 by dannyaudian

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, cint
from frappe.utils.background_jobs import get_jobs

# Import centralized validator functions
from payroll_indonesia.utilities.salary_slip_validator import (
    get_salary_slip_with_validation,
    debug_log,
    check_salary_slip_cancellation,
)


def is_job_already_queued(job_name, queue="default"):
    """
    Check if a job with the specified name is already queued

    Args:
        job_name: The name of the job to check
        queue: The queue to check (default, long, short)

    Returns:
        bool: True if the job is already queued, False otherwise
    """
    try:
        jobs = get_jobs(site=frappe.local.site, queue=queue)
        return any(job.get("kwargs", {}).get("job_name") == job_name for job in jobs)
    except Exception as e:
        frappe.log_error(
            f"Error checking if job {job_name} is queued: {str(e)}", "Job Queue Check Error"
        )
        return False


class EmployeeTaxSummary(Document):
    def validate(self):
        """Validate the employee tax summary with improved error handling"""
        try:
            # Validate required fields
            self.validate_required_fields()

            # Check for duplicates
            self.validate_duplicate()

            # Set document title
            self.set_title()

            # Calculate YTD from monthly entries
            self.calculate_ytd_from_monthly()

            # Validate monthly details
            self.validate_monthly_details()

        except Exception as e:
            frappe.log_error(
                f"Error validating Employee Tax Summary {self.name}: {str(e)}",
                "Employee Tax Summary Validation Error",
            )
            # Re-throw with user-friendly message
            frappe.throw(_("Error validating tax summary: {0}").format(str(e)))

    def validate_required_fields(self):
        """Validate that all required fields are present"""
        # Check employee is specified
        if not self.employee:
            frappe.throw(_("Employee is mandatory for Employee Tax Summary"))

        # Check year is specified
        if not self.year:
            frappe.throw(_("Tax year is mandatory for Employee Tax Summary"))

        # Validate year is a reasonable value
        current_year = getdate().year
        if self.year < 2000 or self.year > current_year + 1:
            frappe.throw(
                _("Invalid tax year: {0}. Must be between 2000 and {1}").format(
                    self.year, current_year + 1
                )
            )

    def validate_duplicate(self):
        """Check if another record exists for the same employee and year"""
        try:
            # Skip check for new records
            if self.is_new():
                return

            existing = frappe.db.exists(
                "Employee Tax Summary",
                {"name": ["!=", self.name], "employee": self.employee, "year": self.year},
            )

            if existing:
                frappe.throw(
                    _("Tax summary for employee {0} for year {1} already exists (ID: {2})").format(
                        self.employee_name, self.year, existing
                    )
                )

        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
            frappe.log_error(
                f"Error checking for duplicate tax summaries: {str(e)}",
                "Employee Tax Summary Duplicate Check Error",
            )
            frappe.throw(_("Error checking for duplicate records: {0}").format(str(e)))

    def set_title(self):
        """Set the document title"""
        try:
            if not self.employee_name:
                # Try to get employee name if not set
                self.employee_name = frappe.db.get_value("Employee", self.employee, "employee_name")
                if not self.employee_name:
                    self.employee_name = self.employee

            self.title = f"{self.employee_name} - {self.year}"
        except Exception as e:
            frappe.log_error(
                f"Error setting title for Employee Tax Summary {self.name}: {str(e)}",
                "Title Setting Error",
            )
            # Don't throw here, just set a default title
            self.title = f"{self.employee} - {self.year}"

    def validate_monthly_details(self):
        """Validate monthly details are consistent"""
        if not self.monthly_details:
            return

        try:
            # Check for duplicate months
            months = {}
            for d in self.monthly_details:
                if not d.month:
                    frappe.throw(_("Month is required in row {0}").format(d.idx))

                if d.month < 1 or d.month > 12:
                    frappe.throw(_("Invalid month {0} in row {1}").format(d.month, d.idx))

                if d.month in months:
                    frappe.throw(
                        _("Duplicate month {0} in rows {1} and {2}").format(
                            d.month, months[d.month], d.idx
                        )
                    )

                months[d.month] = d.idx

            # Validate monthly data
            for d in self.monthly_details:
                # Ensure gross pay is non-negative
                if flt(d.gross_pay) < 0:
                    frappe.msgprint(
                        _("Negative gross pay {0} in month {1}, setting to 0").format(
                            d.gross_pay, d.month
                        )
                    )
                    d.gross_pay = 0

                # Ensure tax amount is non-negative
                if flt(d.tax_amount) < 0:
                    frappe.msgprint(
                        _("Negative tax amount {0} in month {1}, setting to 0").format(
                            d.tax_amount, d.month
                        )
                    )
                    d.tax_amount = 0

                # Validate TER rate if using TER
                if cint(d.is_using_ter) and (flt(d.ter_rate) <= 0 or flt(d.ter_rate) > 50):
                    frappe.msgprint(
                        _("Invalid TER rate {0}% in month {1}, should be between 0-50%").format(
                            d.ter_rate, d.month
                        )
                    )

        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
            frappe.log_error(
                f"Error validating monthly details for Employee Tax Summary {self.name}: {str(e)}",
                "Monthly Details Validation Error",
            )
            frappe.throw(_("Error validating monthly details: {0}").format(str(e)))

    def calculate_ytd_from_monthly(self):
        """Calculate YTD tax amount from monthly details"""
        try:
            if not self.monthly_details:
                self.ytd_tax = 0
                return

            total_tax = 0
            for monthly in self.monthly_details:
                if hasattr(monthly, "tax_amount"):
                    total_tax += flt(monthly.tax_amount)

            self.ytd_tax = total_tax

        except Exception as e:
            frappe.log_error(
                f"Error calculating YTD from monthly for {self.name}: {str(e)}",
                "YTD Calculation Error",
            )
            frappe.throw(_("Error calculating year-to-date tax amount: {0}").format(str(e)))

    def add_monthly_data(self, salary_slip):
        """
        Add or update monthly tax data from salary slip with improved error handling

        Args:
            salary_slip: The salary slip document to get tax data from
        """
        try:
            # Validate salary slip
            if not salary_slip or not hasattr(salary_slip, "start_date"):
                frappe.throw(_("Invalid salary slip provided"))

            month = getdate(salary_slip.start_date).month
            year = getdate(salary_slip.start_date).year

            # Validate year matches
            if year != self.year:
                frappe.throw(
                    _("Salary slip year ({0}) doesn't match tax summary year ({1})").format(
                        year, self.year
                    )
                )

            # Extract data from salary slip
            tax_data = self._extract_tax_data_from_slip(salary_slip)

            # Check if month already exists in monthly details
            existing_month = None
            for i, d in enumerate(self.monthly_details):
                if hasattr(d, "month") and d.month == month:
                    existing_month = i
                    break

            if existing_month is not None:
                # Update existing month
                self._update_existing_month(existing_month, salary_slip.name, tax_data)
            else:
                # Add new month
                self._add_new_month(month, salary_slip.name, tax_data)

            # Recalculate YTD
            self.calculate_ytd_from_monthly()

            # Save document with error handling
            self._save_with_error_handling()

            # Log successful update
            debug_log(
                f"Successfully updated monthly data for {self.name}, month={month}, slip={salary_slip.name}"
            )

        except Exception as e:
            if isinstance(e, frappe.exceptions.ValidationError):
                raise
            frappe.log_error(
                f"Error adding monthly data to tax summary {self.name} from salary slip {getattr(salary_slip, 'name', 'unknown')}: {str(e)}",
                "Monthly Data Addition Error",
            )
            frappe.throw(_("Error adding monthly data to tax summary: {0}").format(str(e)))

    def _extract_tax_data_from_slip(self, salary_slip):
        """
        Extract tax-related data from salary slip

        Args:
            salary_slip: The salary slip document

        Returns:
            dict: Dictionary with tax data extracted from salary slip
        """
        # Initialize values
        pph21_amount = 0
        bpjs_deductions = 0
        other_deductions = 0

        # Get tax amount from salary slip
        if hasattr(salary_slip, "deductions"):
            for deduction in salary_slip.deductions:
                if deduction.salary_component == "PPh 21":
                    pph21_amount = flt(deduction.amount)
                elif deduction.salary_component in [
                    "BPJS JHT Employee",
                    "BPJS JP Employee",
                    "BPJS Kesehatan Employee",
                ]:
                    bpjs_deductions += flt(deduction.amount)
                else:
                    other_deductions += flt(deduction.amount)

        # Get gross pay from salary slip, with validation
        gross_pay = 0
        if hasattr(salary_slip, "gross_pay"):
            gross_pay = flt(salary_slip.gross_pay)

        # Get TER information from salary slip
        is_using_ter = 0
        ter_rate = 0
        ter_category = ""
        biaya_jabatan = 0
        netto = 0
        annual_taxable_income = 0
        monthly_gross_for_ter = 0

        if hasattr(salary_slip, "is_using_ter") and salary_slip.is_using_ter:
            is_using_ter = 1
            if hasattr(salary_slip, "ter_rate"):
                ter_rate = flt(salary_slip.ter_rate)
            if hasattr(salary_slip, "ter_category"):
                ter_category = salary_slip.ter_category

        # Get additional tax calculation fields
        if hasattr(salary_slip, "biaya_jabatan"):
            biaya_jabatan = flt(salary_slip.biaya_jabatan)
        if hasattr(salary_slip, "netto"):
            netto = flt(salary_slip.netto)
        if hasattr(salary_slip, "annual_taxable_income"):
            annual_taxable_income = flt(salary_slip.annual_taxable_income)
        if hasattr(salary_slip, "monthly_gross_for_ter"):
            monthly_gross_for_ter = flt(salary_slip.monthly_gross_for_ter)

        # Return extracted data
        return {
            "pph21_amount": pph21_amount,
            "bpjs_deductions": bpjs_deductions,
            "other_deductions": other_deductions,
            "gross_pay": gross_pay,
            "is_using_ter": is_using_ter,
            "ter_rate": ter_rate,
            "ter_category": ter_category,
            "biaya_jabatan": biaya_jabatan,
            "netto": netto,
            "annual_taxable_income": annual_taxable_income,
            "monthly_gross_for_ter": monthly_gross_for_ter,
        }

    def _update_existing_month(self, month_index, salary_slip_name, tax_data):
        """
        Update an existing monthly detail record

        Args:
            month_index: Index of the month in monthly_details
            salary_slip_name: Name of the salary slip document
            tax_data: Dictionary with tax data
        """
        # Store salary slip reference
        self.monthly_details[month_index].salary_slip = salary_slip_name

        # Update basic fields
        self.monthly_details[month_index].gross_pay = tax_data["gross_pay"]
        self.monthly_details[month_index].bpjs_deductions = tax_data["bpjs_deductions"]
        self.monthly_details[month_index].other_deductions = tax_data["other_deductions"]
        self.monthly_details[month_index].tax_amount = tax_data["pph21_amount"]

        # Update TER information
        self.monthly_details[month_index].is_using_ter = tax_data["is_using_ter"]
        self.monthly_details[month_index].ter_rate = tax_data["ter_rate"]

        # Update additional calculation fields if they exist
        for field in ["ter_category", "biaya_jabatan", "netto", "annual_taxable_income"]:
            if hasattr(self.monthly_details[month_index], field) and field in tax_data:
                setattr(self.monthly_details[month_index], field, tax_data[field])

    def _add_new_month(self, month, salary_slip_name, tax_data):
        """
        Add a new monthly detail record

        Args:
            month: Month number (1-12)
            salary_slip_name: Name of the salary slip document
            tax_data: Dictionary with tax data
        """
        # Create new monthly detail with salary slip reference
        monthly_data = {
            "month": month,
            "salary_slip": salary_slip_name,  # Store salary slip reference
            "gross_pay": tax_data["gross_pay"],
            "bpjs_deductions": tax_data["bpjs_deductions"],
            "other_deductions": tax_data["other_deductions"],
            "tax_amount": tax_data["pph21_amount"],
            "is_using_ter": tax_data["is_using_ter"],
            "ter_rate": tax_data["ter_rate"],
        }

        # Add additional calculation fields if available
        for field in ["ter_category", "biaya_jabatan", "netto", "annual_taxable_income"]:
            if field in tax_data:
                monthly_data[field] = tax_data[field]

        # Append to monthly details
        self.append("monthly_details", monthly_data)

    def _save_with_error_handling(self):
        """Save the document with proper error handling"""
        try:
            self.flags.ignore_validate_update_after_submit = True
            self.flags.ignore_permissions = True
            self.save()
        except Exception as e:
            frappe.log_error(
                f"Error saving tax summary {self.name} after adding monthly data: {str(e)}",
                "Tax Summary Save Error",
            )
            frappe.throw(_("Error saving tax summary: {0}").format(str(e)))

    def reset_monthly_data(self, month, salary_slip=None):
        """
        Reset monthly data for a specific month and salary slip

        Args:
            month: Month number (1-12) to reset
            salary_slip: Optional salary slip name to match

        Returns:
            bool: True if data was reset, False otherwise
        """
        changed = False
        for i, d in enumerate(self.monthly_details):
            if getattr(d, "month") == month:
                if salary_slip and getattr(d, "salary_slip") != salary_slip:
                    continue

                # Reset values for this month
                d.gross_pay = 0
                d.bpjs_deductions = 0
                d.other_deductions = 0
                d.tax_amount = 0
                d.salary_slip = None
                d.is_using_ter = 0
                d.ter_rate = 0

                # Reset additional fields if they exist
                for field in ["ter_category", "biaya_jabatan", "netto", "annual_taxable_income"]:
                    if hasattr(d, field):
                        setattr(d, field, "" if field == "ter_category" else 0)

                changed = True
                break

        return changed

    def get_ytd_data_until_month(self, month):
        """
        Get YTD data until specified month with improved error handling

        Args:
            month: Month to get data until (1-12)

        Returns:
            dict: Dictionary containing YTD data with keys:
                - gross: Total gross pay
                - bpjs: Total BPJS deductions
                - pph21: Total PPh 21 paid
                - net: Total net pay (if available)
                - monthly_amounts: List of monthly amounts
        """
        result = {"gross": 0, "bpjs": 0, "pph21": 0, "net": 0, "monthly_amounts": []}

        try:
            # Validate month parameter
            if not month or not isinstance(month, int) or month < 1 or month > 12:
                frappe.throw(_("Invalid month {0}. Must be between 1-12.").format(month))

            if not self.monthly_details:
                return result

            for monthly in self.monthly_details:
                if hasattr(monthly, "month") and monthly.month <= month:
                    result["gross"] += flt(monthly.gross_pay)
                    result["bpjs"] += flt(monthly.bpjs_deductions)
                    result["pph21"] += flt(monthly.tax_amount)

                    # Get net amount if available
                    if hasattr(monthly, "netto"):
                        result["net"] += flt(monthly.netto)

                    # Add to monthly amounts list
                    result["monthly_amounts"].append(
                        {
                            "month": monthly.month,
                            "gross": flt(monthly.gross_pay),
                            "tax": flt(monthly.tax_amount),
                            "bpjs": flt(monthly.bpjs_deductions),
                        }
                    )

            return result

        except Exception as e:
            frappe.log_error(
                f"Error getting YTD data until month {month} for tax summary {self.name}: {str(e)}",
                "YTD Data Retrieval Error",
            )
            # Instead of throwing, return empty result on error
            return {"gross": 0, "bpjs": 0, "pph21": 0, "net": 0, "monthly_amounts": []}

    def delete_tax_summary(self):
        """
        Delete this tax summary and all related monthly details.

        This method provides a clean way to remove all tax summary data for a
        specific employee and year when needed (e.g., in case of major data corruption).

        Note: This is a destructive operation and should be used with caution.
        """
        try:
            # Log the deletion for audit purposes
            debug_log(
                f"Starting deletion of Employee Tax Summary {self.name} for employee {self.employee}, year {self.year}",
                level="warning",
            )

            # First, handle monthly details
            monthly_details_deleted = 0

            # Delete monthly details one by one
            for row in self.monthly_details:
                if row.name:
                    frappe.delete_doc(
                        "Employee Monthly Tax Detail",
                        row.name,
                        force=True,
                        ignore_permissions=True,
                        ignore_on_trash=True,
                    )
                    monthly_details_deleted += 1

            # Then delete the tax summary itself
            frappe.delete_doc(
                "Employee Tax Summary",
                self.name,
                force=True,
                ignore_permissions=True,
                ignore_on_trash=True,
            )

            # Log successful deletion
            debug_log(
                f"Successfully deleted Employee Tax Summary {self.name} with {monthly_details_deleted} monthly records",
                level="warning",
            )

            return {
                "status": "success",
                "message": f"Successfully deleted tax summary with {monthly_details_deleted} monthly records",
                "monthly_details_deleted": monthly_details_deleted,
            }

        except Exception as e:
            frappe.log_error(
                f"Error deleting tax summary {self.name}: {str(e)}\n{frappe.get_traceback()}",
                "Tax Summary Deletion Error",
            )
            frappe.throw(_("Error deleting tax summary: {0}").format(str(e)))

    def on_update(self):
        """Actions after updating tax summary"""
        try:
            # Update title if not set
            if not self.title:
                self.set_title()
                self.db_set("title", self.title, update_modified=False)

            # Update TER indicator at year level if any month uses TER
            has_ter = False
            max_ter_rate = 0

            if hasattr(self, "monthly_details") and self.monthly_details:
                for monthly in self.monthly_details:
                    if cint(monthly.is_using_ter):
                        has_ter = True
                        max_ter_rate = max(max_ter_rate, flt(monthly.ter_rate))

            # Update TER fields if they exist
            if hasattr(self, "is_using_ter"):
                self.db_set("is_using_ter", 1 if has_ter else 0, update_modified=False)

            if hasattr(self, "ter_rate") and has_ter:
                self.db_set("ter_rate", max_ter_rate, update_modified=False)

        except Exception as e:
            frappe.log_error(
                f"Error in on_update for Employee Tax Summary {self.name}: {str(e)}",
                "Employee Tax Summary Update Error",
            )


# ----- Fungsi tambahan untuk integrasi dengan Salary Slip -----


@frappe.whitelist()
def create_from_salary_slip(salary_slip, method=None):
    """
    Create or update Employee Tax Summary from a Salary Slip
    Called asynchronously from the Salary Slip's on_submit method

    Args:
        salary_slip: The name of the salary slip document
        method: Optional callback method name (not used, kept for compatibility)

    Returns:
        str: Name of the created/updated Employee Tax Summary or None on error
    """
    debug_log(f"Starting create_from_salary_slip for {salary_slip}")

    try:
        # Check if job is already running
        job_name = f"tax_summary_update_{salary_slip}"
        if is_job_already_queued(job_name, queue="long") and method != "reprocess":
            debug_log(f"Job {job_name} is already queued or running, skipping...")
            return None

        # Get the salary slip document with proper validation using central validator
        slip = get_salary_slip_with_validation(salary_slip)
        if not slip:
            # Validator already logged the specific error
            debug_log(
                f"Validation failed for salary slip {salary_slip}, aborting tax summary creation"
            )
            return None

        # Additional validation for submitted status
        if slip.docstatus != 1:
            debug_log(
                f"Salary slip {salary_slip} is not submitted (docstatus={slip.docstatus}), aborting tax summary creation"
            )
            return None

        employee = slip.employee
        year = getdate(slip.end_date).year
        month = getdate(slip.end_date).month

        debug_log(f"Processing tax summary for employee={employee}, year={year}, month={month}")

        # Get or create tax summary
        tax_summary = _get_or_create_tax_summary(employee, year)
        if not tax_summary:
            return None

        # Update tax summary with data from salary slip
        tax_summary.add_monthly_data(slip)

        debug_log(f"Successfully processed Employee Tax Summary: {tax_summary.name}")

        return tax_summary.name

    except Exception as e:
        debug_log(
            f"Error in create_from_salary_slip: {str(e)}\nTraceback: {frappe.get_traceback()}"
        )
        frappe.log_error(
            f"Error creating Employee Tax Summary from {salary_slip}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Employee Tax Summary Error",
        )
        return None


def _get_or_create_tax_summary(employee, year):
    """
    Get existing tax summary or create a new one

    Args:
        employee: Employee code
        year: Tax year

    Returns:
        Document: Employee Tax Summary document or None on error
    """
    try:
        # Check if an Employee Tax Summary already exists
        tax_summary_name = frappe.db.get_value(
            "Employee Tax Summary", {"employee": employee, "year": year}
        )

        if tax_summary_name:
            debug_log(f"Found existing Employee Tax Summary: {tax_summary_name}")
            tax_summary = frappe.get_doc("Employee Tax Summary", tax_summary_name)
        else:
            debug_log(f"Creating new Employee Tax Summary for {employee}, {year}")
            tax_summary = _create_new_tax_summary(employee, year)

        return tax_summary

    except Exception as e:
        debug_log(f"Error getting or creating tax summary for {employee}, {year}: {str(e)}")
        frappe.log_error(
            f"Error getting or creating tax summary for {employee}, {year}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Employee Tax Summary Error",
        )
        return None


def _create_new_tax_summary(employee, year):
    """
    Create a new Employee Tax Summary document

    Args:
        employee: Employee code
        year: Tax year

    Returns:
        Document: Newly created Employee Tax Summary
    """
    # Create a new document
    tax_summary = frappe.new_doc("Employee Tax Summary")
    tax_summary.employee = employee
    tax_summary.year = year

    # Get employee details
    emp_doc = frappe.get_doc("Employee", employee)
    if emp_doc:
        tax_summary.employee_name = emp_doc.employee_name

        # Copy fields if they exist in the employee document
        for field in ["department", "designation", "npwp", "ptkp_status", "ktp"]:
            if hasattr(emp_doc, field):
                if hasattr(tax_summary, field):
                    setattr(tax_summary, field, getattr(emp_doc, field))

    # Initialize monthly details
    tax_summary.monthly_details = []
    for i in range(1, 13):
        tax_summary.append(
            "monthly_details",
            {
                "month": i,
                "gross_pay": 0,
                "bpjs_deductions": 0,
                "tax_amount": 0,
                "is_using_ter": 0,
                "ter_rate": 0,
                "salary_slip": None,  # Explicitly initialize salary_slip reference
            },
        )

    # Insert the new document with error handling
    try:
        tax_summary.insert(ignore_permissions=True)
        return tax_summary
    except Exception as e:
        debug_log(f"Error creating new tax summary for {employee}, {year}: {str(e)}")
        frappe.log_error(
            f"Error creating new tax summary for {employee}, {year}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Tax Summary Creation Error",
        )
        return None


@frappe.whitelist()
def update_on_salary_slip_cancel(salary_slip, year):
    """
    Update Employee Tax Summary when a Salary Slip is cancelled
    Called asynchronously from the Salary Slip's on_cancel method

    Args:
        salary_slip: The name of the salary slip document
        year: The tax year to update

    Returns:
        bool: True if updated successfully, False otherwise
    """
    debug_log(f"Starting update_on_salary_slip_cancel for {salary_slip}, year={year}")

    try:
        # Check if job is already running
        job_name = f"tax_summary_revert_{salary_slip}"
        if is_job_already_queued(job_name, queue="long"):
            debug_log(f"Job {job_name} is already queued or running, skipping...")
            return False

        # Use the centralized validator to check the salary slip
        result = check_salary_slip_cancellation(salary_slip)
        if not result["is_cancelled"]:
            debug_log(f"Validation failed for cancelled salary slip: {result['error']}")
            return False

        # Extract employee and month from validated salary slip
        slip = result["slip"]
        employee = slip.employee
        month = result["month"]

        # Validate year is a number
        try:
            year = int(year)
        except (ValueError, TypeError):
            debug_log(f"Invalid year value: {year}")
            return False

        # Find the Employee Tax Summary
        tax_summary_name = frappe.db.get_value(
            "Employee Tax Summary", {"employee": employee, "year": year}
        )

        if not tax_summary_name:
            debug_log(f"No Employee Tax Summary found for employee={employee}, year={year}")
            return False

        # Get the document
        tax_doc = frappe.get_doc("Employee Tax Summary", tax_summary_name)

        # Update the monthly entry for this salary slip
        changed = tax_doc.reset_monthly_data(month, salary_slip)

        # Recalculate YTD if changes were made
        if changed:
            debug_log(f"Recalculating YTD tax for Employee Tax Summary {tax_summary_name}")
            tax_doc.calculate_ytd_from_monthly()

            # Save the document
            tax_doc.flags.ignore_validate_update_after_submit = True
            tax_doc.flags.ignore_permissions = True
            tax_doc.save()
            debug_log(f"Successfully updated Employee Tax Summary: {tax_summary_name}")

            return True
        else:
            debug_log(f"No changes needed for Employee Tax Summary: {tax_summary_name}")
            return False

    except Exception as e:
        debug_log(
            f"Error in update_on_salary_slip_cancel: {str(e)}\nTraceback: {frappe.get_traceback()}"
        )
        frappe.log_error(
            f"Error updating Employee Tax Summary on cancel for {salary_slip}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Employee Tax Summary Cancel Error",
        )
        return False


@frappe.whitelist()
def refresh_tax_summary(employee, year=None, force=False):
    """
    Refresh the tax summary for an employee by recalculating from all salary slips

    Args:
        employee: Employee code
        year: Optional tax year (defaults to current year)
        force: Whether to force recreation of the tax summary

    Returns:
        dict: Status and details of the operation
    """
    try:
        # Set default year if not provided
        if not year:
            year = getdate().year

        # Convert year to integer
        try:
            year = int(year)
        except (ValueError, TypeError):
            return {"status": "error", "message": f"Invalid year value: {year}"}

        # Get all submitted salary slips for this employee and year
        salary_slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": employee,
                "docstatus": 1,
                "start_date": [">=", f"{year}-01-01"],
                "end_date": ["<=", f"{year}-12-31"],
            },
            fields=["name", "start_date", "end_date"],
        )

        if not salary_slips:
            return {
                "status": "error",
                "message": f"No submitted salary slips found for {employee} in {year}",
            }

        # Check if tax summary exists
        tax_summary_name = frappe.db.get_value(
            "Employee Tax Summary", {"employee": employee, "year": year}
        )

        # If force is true and tax summary exists, delete it
        if force and tax_summary_name:
            try:
                tax_summary = frappe.get_doc("Employee Tax Summary", tax_summary_name)
                # Use our new centralized method to safely delete all related data
                tax_summary.delete_tax_summary()
                tax_summary_name = None
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Error deleting existing tax summary: {str(e)}",
                }

        # Create new tax summary if it doesn't exist
        if not tax_summary_name:
            tax_summary = _create_new_tax_summary(employee, year)
            if not tax_summary:
                return {"status": "error", "message": "Failed to create new tax summary"}
            tax_summary_name = tax_summary.name
        else:
            # Reset all monthly data if not force-recreating
            tax_summary = frappe.get_doc("Employee Tax Summary", tax_summary_name)
            for month in range(1, 13):
                tax_summary.reset_monthly_data(month)

            # Save the reset document
            tax_summary.flags.ignore_validate_update_after_submit = True
            tax_summary.flags.ignore_permissions = True
            tax_summary.save()

        # Process each salary slip - using our centralized validation
        processed = 0
        for slip in salary_slips:
            # Validate slip through central validator
            slip_doc = get_salary_slip_with_validation(slip.name)
            if slip_doc:
                result = create_from_salary_slip(slip.name, "reprocess")
                if result:
                    processed += 1

        return {
            "status": "success",
            "message": f"Refreshed tax summary with {processed} of {len(salary_slips)} salary slips",
            "tax_summary": tax_summary_name,
            "processed": processed,
            "total_slips": len(salary_slips),
        }

    except Exception as e:
        frappe.log_error(
            f"Error refreshing tax summary for {employee}, {year}: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Tax Summary Refresh Error",
        )
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_tax_summary_stats(employee=None, year=None):
    """
    Get statistics about tax summaries

    Args:
        employee: Optional employee to filter by
        year: Optional year to filter by

    Returns:
        dict: Statistics about tax summaries
    """
    try:
        filters = {}
        if employee:
            filters["employee"] = employee
        if year:
            try:
                filters["year"] = int(year)
            except (ValueError, TypeError):
                return {"status": "error", "message": f"Invalid year value: {year}"}

        # Get count of tax summaries
        total_summaries = frappe.db.count("Employee Tax Summary", filters)

        # Get total tax paid
        total_tax = 0
        if total_summaries > 0:
            summaries = frappe.get_all("Employee Tax Summary", filters=filters, fields=["ytd_tax"])
            for summary in summaries:
                total_tax += flt(summary.ytd_tax)

        # Get stats by year if no specific year was requested
        year_stats = []
        if not year:
            years = frappe.db.sql(
                """
                SELECT DISTINCT year
                FROM `tabEmployee Tax Summary`
                ORDER BY year DESC
            """,
                as_dict=True,
            )

            for yr in years:
                yr_filters = dict(filters)
                yr_filters["year"] = yr.year
                year_count = frappe.db.count("Employee Tax Summary", yr_filters)

                year_stats.append({"year": yr.year, "count": year_count})

        return {
            "status": "success",
            "total_summaries": total_summaries,
            "total_tax": total_tax,
            "years": year_stats,
        }

    except Exception as e:
        frappe.log_error(
            f"Error getting tax summary stats: {str(e)}\n\n" f"Traceback: {frappe.get_traceback()}",
            "Tax Summary Stats Error",
        )
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def validate(doc):
    """
    Module-level validate function that delegates to the document's validate method
    This is needed for compatibility with code that calls this function directly
    """
    try:
        if isinstance(doc, str):
            doc = frappe.get_doc("Employee Tax Summary", doc)

        # Ensure we have a document instance with a validate method
        if hasattr(doc, "validate") and callable(doc.validate):
            doc.validate()
            return True
        else:
            frappe.log_error(
                "Invalid document passed to validate function",
                "Employee Tax Summary Validation Error",
            )
            return False
    except Exception as e:
        frappe.log_error(
            f"Error in Employee Tax Summary validation: {str(e)}\n\n"
            f"Traceback: {frappe.get_traceback()}",
            "Employee Tax Summary Validation Error",
        )
        return False
