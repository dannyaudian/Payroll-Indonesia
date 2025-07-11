# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Employee Tax Summary management for Indonesian payroll.

This module handles the creation, updating, and management of Employee Tax Summary records
which track annual tax payments and related information for employees. It provides
functionality for:

1. Creating and retrieving tax summaries for employees
2. Updating summaries when salary slips are submitted or cancelled
3. Managing monthly detail records and calculating YTD totals
4. Handling TER (Tax Exemption Ratio) data
5. Managing December tax corrections
"""

from typing import Dict, Any, Optional, List, Union
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, cint

from payroll_indonesia.frappe_helpers import get_logger

logger = get_logger("employee_tax_summary")


class EmployeeTaxSummary(Document):
    """
    Employee Tax Summary document class for tracking annual tax information.
    
    This document stores yearly tax data for an employee with monthly breakdowns
    in the child table 'monthly_details'. It provides methods to update, reset,
    and calculate totals across months.
    """
    
    def validate(self) -> None:
        """Validate the document before saving."""
        try:
            self._validate_required_fields()
            self._validate_duplicate()
            self._set_title()
            self.update_totals()
            self._validate_monthly_details()
        except Exception as e:
            logger.error(f"Error validating Employee Tax Summary {self.name}: {str(e)}")
            logger.error(f"Traceback: {frappe.get_traceback()}")
            frappe.throw(_("Error validating tax summary: {0}").format(str(e)))

    def _validate_required_fields(self) -> None:
        """Ensure required fields are present and valid."""
        if not self.employee:
            frappe.throw(_("Employee is mandatory for Employee Tax Summary"))
            
        if not self.year:
            frappe.throw(_("Year is mandatory for Employee Tax Summary"))
            
        try:
            year_val = int(self.year)
            if year_val < 2000 or year_val > 2100:
                frappe.throw(_("Year must be between 2000 and 2100"))
        except (ValueError, TypeError):
            frappe.throw(_("Invalid year value: {0}").format(self.year))

    def _validate_duplicate(self) -> None:
        """Check for duplicate tax summary records."""
        if self.is_new():
            return
            
        existing = frappe.db.exists(
            "Employee Tax Summary",
            {
                "name": ["!=", self.name],
                "employee": self.employee,
                "year": self.year
            }
        )
        
        if existing:
            frappe.throw(
                _("Tax summary for employee {0} for year {1} already exists (ID: {2})").format(
                    self.employee_name or self.employee, self.year, existing
                )
            )

    def _set_title(self) -> None:
        """Set the document title based on employee and year."""
        if not self.employee_name:
            self.employee_name = frappe.db.get_value(
                "Employee", self.employee, "employee_name"
            ) or self.employee
            
        self.title = f"{self.employee_name} - {self.year}"

    def _validate_monthly_details(self) -> None:
        """Validate monthly detail records."""
        if not self.monthly_details:
            return
            
        months_seen = {}
        for detail in self.monthly_details:
            # Validate month value
            if not detail.month:
                frappe.throw(_("Month is required in row {0}").format(detail.idx))
                
            if detail.month < 1 or detail.month > 12:
                frappe.throw(_("Invalid month {0} in row {1}").format(detail.month, detail.idx))
                
            # Check for duplicates
            if detail.month in months_seen:
                frappe.throw(
                    _("Duplicate month {0} in rows {1} and {2}").format(
                        detail.month, months_seen[detail.month], detail.idx
                    )
                )
                
            months_seen[detail.month] = detail.idx
            
            # Ensure non-negative values
            if flt(detail.gross_pay) < 0:
                detail.gross_pay = 0
                
            if flt(detail.tax_amount) < 0:
                detail.tax_amount = 0
                
            # Validate TER rate if applicable
            if cint(detail.is_using_ter) and (
                flt(detail.ter_rate) <= 0 or flt(detail.ter_rate) > 50
            ):
                frappe.msgprint(
                    _("Invalid TER rate {0}% in month {1}").format(detail.ter_rate, detail.month)
                )

    def update_month(self, slip: Document) -> None:
        """
        Update monthly tax detail from a salary slip.
        
        Args:
            slip: Salary Slip document to extract data from
        """
        try:
            # Validate input
            if not slip or not hasattr(slip, "employee") or slip.employee != self.employee:
                logger.error(f"Invalid salary slip provided for {self.name}")
                return
                
            # Determine month from slip
            month = None
            if hasattr(slip, "posting_date") and slip.posting_date:
                month = getdate(slip.posting_date).month
            elif hasattr(slip, "start_date") and slip.start_date:
                month = getdate(slip.start_date).month
                
            if not month:
                logger.error(f"Could not determine month from slip {slip.name}")
                return
                
            # Check for December correction override
            is_december_override = False
            if hasattr(slip, "is_december_override") and cint(slip.is_december_override) == 1:
                is_december_override = True
                # Force month to December for tax correction
                month = 12
                logger.info(f"December correction override for slip {slip.name}, forcing month to 12")
                
            # Extract values from slip
            values = self._extract_slip_values(slip)
            
            # Find or create monthly detail
            detail = None
            for row in self.monthly_details:
                if row.month == month:
                    detail = row
                    break
                    
            if not detail:
                detail = self.append("monthly_details", {"month": month})
                
            # Update fields
            detail.gross_pay = values["gross_pay"]
            detail.tax_amount = values["tax_amount"]
            detail.bpjs_deductions_employee = values["bpjs_amount"]
            detail.other_deductions = values["other_deductions"]
            detail.salary_slip = slip.name
            detail.is_using_ter = values["is_using_ter"]
            detail.ter_rate = values["ter_rate"]
            
            # Update tax correction field if December override
            if is_december_override and hasattr(detail, "tax_correction"):
                correction_amount = 0
                # Get from koreksi_pph21 field if available
                if hasattr(slip, "koreksi_pph21"):
                    correction_amount = flt(slip.koreksi_pph21)
                
                detail.tax_correction = correction_amount
                logger.info(f"Updated December tax correction to {correction_amount} for {slip.name}")
                
                # If we have a correction description field, set it
                if hasattr(detail, "correction_note") and correction_amount != 0:
                    detail.correction_note = "Koreksi Pajak Akhir Tahun"
                
            # Update additional fields if they exist
            for field, value in values.items():
                if hasattr(detail, field) and field not in [
                    "gross_pay", "tax_amount", "bpjs_amount", "other_deductions",
                    "is_using_ter", "ter_rate", "salary_slip", "tax_correction"
                ]:
                    setattr(detail, field, value)
                    
            # Recalculate totals
            self.update_totals()
            
            logger.info(
                f"Updated month {month} in tax summary {self.name} "
                f"from slip {slip.name}"
            )
            
        except Exception as e:
            logger.error(f"Failed to update month from slip: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error updating month in tax summary {self.name} from slip {slip.name}: {str(e)}",
                "Tax Summary Update Error"
            )

    def clear_month(self, month: int, slip_name: Optional[str] = None) -> bool:
        """
        Reset data for a specific month.
        
        Args:
            month: Month number (1-12) to reset
            slip_name: Optional slip name to match against
            
        Returns:
            bool: True if data was reset, False otherwise
        """
        try:
            if month < 1 or month > 12:
                logger.warning(f"Invalid month {month} in clear_month")
                return False
                
            changed = False
            for detail in self.monthly_details:
                if detail.month == month:
                    if slip_name and detail.salary_slip != slip_name:
                        continue
                        
                    # Reset values
                    detail.gross_pay = 0
                    detail.tax_amount = 0
                    detail.bpjs_deductions_employee = 0
                    detail.other_deductions = 0
                    detail.salary_slip = ""
                    detail.is_using_ter = 0
                    detail.ter_rate = 0
                    
                    # Reset tax correction fields
                    if hasattr(detail, "tax_correction"):
                        detail.tax_correction = 0
                    if hasattr(detail, "correction_note"):
                        detail.correction_note = ""
                    
                    # Reset additional fields if they exist
                    for field in ["biaya_jabatan", "netto", "annual_taxable_income"]:
                        if hasattr(detail, field):
                            setattr(detail, field, 0)
                    
                    if hasattr(detail, "ter_category"):
                        detail.ter_category = ""
                        
                    changed = True
                    logger.info(f"Cleared month {month} in tax summary {self.name}")
                    break
                    
            # Recalculate totals if changes were made
            if changed:
                self.update_totals()
                
            return changed
            
        except Exception as e:
            logger.error(f"Failed to clear month: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error clearing month {month} in tax summary {self.name}: {str(e)}",
                "Tax Summary Clear Error"
            )
            return False

    def update_totals(self) -> None:
        """Calculate and update year-to-date totals from monthly details."""
        try:
            ytd_gross = 0
            ytd_tax = 0
            ytd_bpjs = 0
            ytd_other = 0
            ytd_tax_correction = 0
            
            for detail in self.monthly_details or []:
                ytd_gross += flt(detail.gross_pay)
                ytd_tax += flt(detail.tax_amount)
                ytd_bpjs += flt(getattr(detail, "bpjs_deductions_employee", 0))
                ytd_other += flt(getattr(detail, "other_deductions", 0))
                
                # Add tax correction if present
                if hasattr(detail, "tax_correction"):
                    ytd_tax_correction += flt(detail.tax_correction)
            
            self.ytd_gross_pay = ytd_gross
            self.ytd_tax = ytd_tax
            self.ytd_bpjs = ytd_bpjs
            
            if hasattr(self, "ytd_other_deductions"):
                self.ytd_other_deductions = ytd_other
                
            # Update total tax correction if field exists
            if hasattr(self, "ytd_tax_correction"):
                self.ytd_tax_correction = ytd_tax_correction
                
            # Update total tax including correction if field exists
            if hasattr(self, "ytd_tax_with_correction"):
                self.ytd_tax_with_correction = ytd_tax + ytd_tax_correction
                
            logger.debug(
                f"Updated totals for {self.name}: gross={ytd_gross}, "
                f"tax={ytd_tax}, bpjs={ytd_bpjs}, correction={ytd_tax_correction}"
            )
            
        except Exception as e:
            logger.error(f"Failed to update totals: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error updating totals for tax summary {self.name}: {str(e)}",
                "Tax Summary Totals Error"
            )

    def _extract_slip_values(self, slip: Document) -> Dict[str, Any]:
        """
        Extract tax-related values from a salary slip.
        
        Args:
            slip: Salary Slip document
            
        Returns:
            Dict: Dictionary of extracted values
        """
        result = {
            "gross_pay": 0,
            "tax_amount": 0,
            "bpjs_amount": 0,
            "other_deductions": 0,
            "is_using_ter": 0,
            "ter_rate": 0,
            "biaya_jabatan": 0,
            "netto": 0,
            "ter_category": "",
            "tax_correction": 0
        }
        
        # Get gross pay
        if hasattr(slip, "gross_pay"):
            result["gross_pay"] = flt(slip.gross_pay)
        
        # Extract deduction values
        if hasattr(slip, "deductions"):
            for deduction in slip.deductions:
                if deduction.salary_component == "PPh 21":
                    result["tax_amount"] = flt(deduction.amount)
                elif deduction.salary_component == "PPh 21 Correction":
                    # Store correction separately
                    result["tax_correction"] = flt(deduction.amount)
                elif deduction.salary_component in [
                    "BPJS JHT Employee",
                    "BPJS JP Employee",
                    "BPJS Kesehatan Employee"
                ]:
                    result["bpjs_amount"] += flt(deduction.amount)
                else:
                    result["other_deductions"] += flt(deduction.amount)
        
        # Get TER information
        if hasattr(slip, "is_using_ter"):
            result["is_using_ter"] = cint(slip.is_using_ter)
        
        if hasattr(slip, "ter_rate"):
            result["ter_rate"] = flt(slip.ter_rate)
        
        if hasattr(slip, "ter_category"):
            result["ter_category"] = slip.ter_category
        
        # Get December correction if available
        if hasattr(slip, "koreksi_pph21"):
            result["tax_correction"] = flt(slip.koreksi_pph21)
        
        # Get additional calculation fields
        for field in ["biaya_jabatan", "netto"]:
            if hasattr(slip, field):
                result[field] = flt(getattr(slip, field))
        
        return result

    def on_update(self) -> None:
        """Perform actions after document is updated."""
        try:
            # Update title if not set
            if not self.title:
                self._set_title()
                self.db_set("title", self.title, update_modified=False)
            
            # Update TER indicator at summary level
            has_ter = False
            max_ter_rate = 0
            
            for detail in self.monthly_details or []:
                if cint(detail.is_using_ter):
                    has_ter = True
                    max_ter_rate = max(max_ter_rate, flt(detail.ter_rate))
            
            # Update summary-level TER fields if they exist
            if hasattr(self, "is_using_ter"):
                self.db_set("is_using_ter", 1 if has_ter else 0, update_modified=False)
                
            if hasattr(self, "ter_rate") and has_ter:
                self.db_set("ter_rate", max_ter_rate, update_modified=False)
                
            # Update December correction indicator if field exists
            if hasattr(self, "has_december_correction"):
                has_correction = False
                for detail in self.monthly_details or []:
                    if detail.month == 12 and hasattr(detail, "tax_correction") and flt(detail.tax_correction) != 0:
                        has_correction = True
                        break
                
                self.db_set("has_december_correction", 1 if has_correction else 0, update_modified=False)
                
        except Exception as e:
            logger.error(f"Failed in on_update: {frappe.get_traceback()}")
            frappe.log_error(
                f"Error in on_update for tax summary {self.name}: {str(e)}",
                "Tax Summary Update Error"
            )


def get_or_create_summary(employee: str, year: int) -> Document:
    """
    Get an existing tax summary or create a new one.
    
    Args:
        employee: Employee ID
        year: Tax year
        
    Returns:
        Document: Employee Tax Summary document
    """
    try:
        # Validate inputs
        if not employee:
            logger.error("Employee is required to get tax summary")
            frappe.throw(_("Employee is required to get tax summary"))
        
        try:
            year = int(year)
        except (ValueError, TypeError):
            logger.error(f"Invalid year value: {year}")
            frappe.throw(_("Invalid year value: {0}").format(year))
        
        # Check if summary exists
        filters = {"employee": employee, "year": year}
        summary_name = frappe.db.get_value("Employee Tax Summary", filters)
        
        if summary_name:
            logger.debug(f"Found existing tax summary: {summary_name}")
            return frappe.get_doc("Employee Tax Summary", summary_name)
        
        # Create new summary
        summary = frappe.new_doc("Employee Tax Summary")
        summary.employee = employee
        summary.year = year
        
        # Get employee details
        emp = frappe.db.get_value(
            "Employee",
            employee,
            ["employee_name", "department", "designation", "npwp", "ptkp_status"],
            as_dict=True
        )
        
        if emp:
            summary.employee_name = emp.employee_name
            
            # Copy fields if they exist
            for field in ["department", "designation", "npwp", "ptkp_status"]:
                if emp.get(field) and hasattr(summary, field):
                    setattr(summary, field, emp.get(field))
        
        # Initialize monthly details
        for month in range(1, 13):
            month_detail = {
                "month": month,
                "gross_pay": 0,
                "tax_amount": 0,
                "bpjs_deductions_employee": 0,
                "other_deductions": 0,
                "is_using_ter": 0,
                "ter_rate": 0
            }
            
            # Add tax_correction field if exists in doctype
            if frappe.get_meta("Employee Tax Summary Detail").has_field("tax_correction"):
                month_detail["tax_correction"] = 0
                
            summary.append("monthly_details", month_detail)
        
        # Insert document
        summary.insert(ignore_permissions=True)
        logger.info(f"Created new tax summary for {employee}, year {year}")
        
        return summary
        
    except Exception as e:
        logger.error(f"Failed to get or create summary: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error getting/creating tax summary for {employee}, year {year}: {str(e)}",
            "Tax Summary Creation Error"
        )
        frappe.throw(_("Error creating tax summary: {0}").format(str(e)))


def update_from_salary_slip(slip_name: str) -> Optional[str]:
    """
    Update Employee Tax Summary from a salary slip.
    
    Args:
        slip_name: Name of the Salary Slip document
        
    Returns:
        Optional[str]: Name of the updated tax summary or None on error
    """
    try:
        # Get the salary slip
        slip = frappe.get_doc("Salary Slip", slip_name)
        
        if not slip.employee:
            logger.warning(f"Slip {slip_name} has no employee, skipping tax summary update")
            return None
        
        # Skip if not submitted
        if slip.docstatus != 1:
            logger.warning(
                f"Slip {slip_name} is not submitted (status={slip.docstatus}), "
                "skipping tax summary update"
            )
            return None
        
        # Determine year
        year = None
        if hasattr(slip, "posting_date") and slip.posting_date:
            year = getdate(slip.posting_date).year
        elif hasattr(slip, "start_date") and slip.start_date:
            year = getdate(slip.start_date).year
            
        if not year:
            logger.error(f"Could not determine year from slip {slip_name}")
            return None
        
        # Get or create summary
        summary = get_or_create_summary(slip.employee, year)
        
        # Update the summary
        summary.update_month(slip)
        
        # Save changes
        summary.flags.ignore_permissions = True
        summary.flags.ignore_validate_update_after_submit = True
        summary.save()
        
        logger.info(f"Updated tax summary {summary.name} from slip {slip_name}")
        
        return summary.name
        
    except Exception as e:
        logger.error(f"Failed to update from salary slip: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error updating tax summary from slip {slip_name}: {str(e)}",
            "Tax Summary Update Error"
        )
        return None


def reset_from_cancelled_slip(slip_name: str) -> bool:
    """
    Reset tax data when a salary slip is cancelled.
    
    Args:
        slip_name: Name of the cancelled Salary Slip document
        
    Returns:
        bool: True if data was reset, False otherwise
    """
    try:
        # Get the salary slip
        slip = frappe.get_doc("Salary Slip", slip_name)
        
        if not slip.employee:
            logger.warning(f"Slip {slip_name} has no employee, skipping tax reset")
            return False
        
        # Skip if not cancelled
        if slip.docstatus != 2:  # 2 = Cancelled
            logger.warning(
                f"Slip {slip_name} is not cancelled (status={slip.docstatus}), "
                "skipping tax reset"
            )
            return False
        
        # Determine month and year
        month = None
        year = None
        
        if hasattr(slip, "start_date") and slip.start_date:
            month = getdate(slip.start_date).month
            year = getdate(slip.start_date).year
        elif hasattr(slip, "posting_date") and slip.posting_date:
            month = getdate(slip.posting_date).month
            year = getdate(slip.posting_date).year
            
        if not month or not year:
            logger.error(f"Could not determine month/year from slip {slip_name}")
            return False
        
        # Check for December override - always reset December for December override slips
        if hasattr(slip, "is_december_override") and cint(slip.is_december_override) == 1:
            month = 12
            logger.info(f"December correction override for cancelled slip {slip_name}, resetting month 12")
        
        # Find tax summary
        summary_name = frappe.db.get_value(
            "Employee Tax Summary",
            {"employee": slip.employee, "year": year}
        )
        
        if not summary_name:
            logger.info(f"No tax summary found for {slip.employee}, year {year}")
            return False
            
        # Get tax summary
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
        
        # Reset the month
        changed = summary.clear_month(month, slip_name)
        
        # Save if changes were made
        if changed:
            summary.flags.ignore_permissions = True
            summary.flags.ignore_validate_update_after_submit = True
            summary.save()
            
            logger.info(f"Reset tax data in {summary_name} for month {month}")
            
        return changed
        
    except Exception as e:
        logger.error(f"Failed to reset from cancelled slip: {frappe.get_traceback()}")
        frappe.log_error(
            f"Error resetting tax data for slip {slip_name}: {str(e)}",
            "Tax Summary Reset Error"
        )
        return False


@frappe.whitelist()
def refresh_tax_summary(employee: str, year: Optional[int] = None) -> Dict[str, Any]:
    """
    Refresh tax summary by recalculating from all salary slips.
    
    Args:
        employee: Employee ID
        year: Optional tax year (defaults to current year)
        
    Returns:
        Dict: Result status and information
    """
    try:
        # Set default year if not provided
        if not year:
            year = getdate().year
            
        # Ensure year is an integer
        try:
            year = int(year)
        except (ValueError, TypeError):
            return {"status": "error", "message": f"Invalid year value: {year}"}
        
        # Get salary slips for this employee and year
        slips = frappe.get_all(
            "Salary Slip",
            filters={
                "employee": employee,
                "docstatus": 1,
                "start_date": [">=", f"{year}-01-01"],
                "end_date": ["<=", f"{year}-12-31"]
            },
            fields=["name"]
        )
        
        if not slips:
            return {
                "status": "error",
                "message": f"No submitted salary slips found for {employee} in {year}"
            }
        
        # Get or create tax summary
        summary = get_or_create_summary(employee, year)
        
        # Reset all months
        for month in range(1, 13):
            summary.clear_month(month)
            
        # Save the reset document
        summary.flags.ignore_permissions = True
        summary.flags.ignore_validate_update_after_submit = True
        summary.save()
        
        # Process each slip
        processed = 0
        for slip in slips:
            if update_from_salary_slip(slip.name):
                processed += 1
                
        return {
            "status": "success",
            "message": f"Refreshed tax summary with {processed} salary slips",
            "tax_summary": summary.name,
            "processed": processed,
            "total_slips": len(slips)
        }
        
    except Exception as e:
        logger.error(f"Failed to refresh tax summary: {frappe.get_traceback()}")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_ytd_data(employee: str, year: int, month: int) -> Dict[str, Any]:
    """
    Get year-to-date tax data up to a specified month.
    
    Args:
        employee: Employee ID
        year: Tax year
        month: Month to calculate up to (1-12)
        
    Returns:
        Dict: YTD data and monthly breakdown
    """
    try:
        # Validate month
        try:
            month = int(month)
            if month < 1 or month > 12:
                return {"status": "error", "message": f"Invalid month: {month}"}
        except (ValueError, TypeError):
            return {"status": "error", "message": f"Invalid month value: {month}"}
            
        # Find tax summary
        summary_name = frappe.db.get_value(
            "Employee Tax Summary",
            {"employee": employee, "year": year}
        )
        
        if not summary_name:
            return {
                "status": "error",
                "message": f"No tax summary found for {employee} in {year}"
            }
            
        # Get tax summary
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
        
        # Calculate YTD totals
        ytd_gross = 0
        ytd_tax = 0
        ytd_bpjs = 0
        ytd_tax_correction = 0
        monthly_data = []
        
        for detail in summary.monthly_details:
            if detail.month <= month:
                ytd_gross += flt(detail.gross_pay)
                ytd_tax += flt(detail.tax_amount)
                ytd_bpjs += flt(detail.bpjs_deductions_employee)
                
                # Include tax correction if available
                tax_correction = flt(getattr(detail, "tax_correction", 0))
                ytd_tax_correction += tax_correction
                
                monthly_data.append({
                    "month": detail.month,
                    "gross_pay": detail.gross_pay,
                    "tax_amount": detail.tax_amount,
                    "bpjs": detail.bpjs_deductions_employee,
                    "is_using_ter": detail.is_using_ter,
                    "ter_rate": detail.ter_rate,
                    "tax_correction": tax_correction
                })
        
        result = {
            "status": "success",
            "employee": employee,
            "year": year,
            "month": month,
            "ytd_gross": ytd_gross,
            "ytd_tax": ytd_tax,
            "ytd_bpjs": ytd_bpjs,
            "monthly_data": monthly_data
        }
        
        # Add tax correction data if available
        if ytd_tax_correction != 0:
            result["ytd_tax_correction"] = ytd_tax_correction
            result["ytd_tax_with_correction"] = ytd_tax + ytd_tax_correction
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get YTD data: {frappe.get_traceback()}")
        return {"status": "error", "message": str(e)}