# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Employee Monthly Tax Detail controller.

This module manages the monthly details of employee tax records, functioning as
a child table of Employee Tax Summary. It handles monthly tax calculations,
maintains data integrity, and provides methods to:

1. Create or update monthly records from Salary Slips
2. Clear data when salary slips are cancelled
3. Validate data to ensure consistency
4. Trigger recalculation of year-to-date totals in the parent document

The module works in conjunction with the Employee Tax Summary to maintain
a complete record of an employee's tax history throughout the year.
"""

from typing import Dict, Any, Optional, Union

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, cint

from payroll_indonesia.frappe_helpers.logger import get_logger

# Set up module logger
logger = get_logger(__name__)


class EmployeeMonthlyTaxDetail(Document):
    """
    Employee Monthly Tax Detail document representing a single month's tax data.
    
    This is a child document of Employee Tax Summary, storing the monthly breakdown
    of tax-related information including gross pay, deductions, and tax payments.
    """
    
    def validate(self) -> None:
        """Validate the monthly tax detail before saving."""
        self.validate_month()
        self.validate_amounts()
        self.validate_ter_data()
    
    def validate_month(self) -> None:
        """Ensure month value is between 1 and 12."""
        if not self.month or self.month < 1 or self.month > 12:
            frappe.throw(_("Month must be between 1 and 12"))
    
    def validate_amounts(self) -> None:
        """Ensure all monetary amounts are non-negative."""
        for field in [
            "gross_pay", 
            "tax_amount", 
            "bpjs_deductions_employee",
            "other_deductions"
        ]:
            if hasattr(self, field) and flt(getattr(self, field)) < 0:
                setattr(self, field, 0)
                frappe.msgprint(
                    _("Negative {0} was reset to 0").format(
                        _(field.replace("_", " ").title())
                    )
                )
    
    def validate_ter_data(self) -> None:
        """Ensure TER data is consistent."""
        # If not using TER, ensure TER rate is 0
        if hasattr(self, "is_using_ter") and not cint(self.is_using_ter):
            self.ter_rate = 0
        
        # Validate TER rate if using TER
        if (
            hasattr(self, "is_using_ter") 
            and cint(self.is_using_ter) 
            and (flt(self.ter_rate) <= 0 or flt(self.ter_rate) > 50)
        ):
            frappe.msgprint(
                _("Invalid TER rate {0}% for month {1}").format(
                    self.ter_rate, self.month
                )
            )
    
    def on_update(self) -> None:
        """Trigger parent document update when this document changes."""
        try:
            if self.parent:
                # Import here to avoid circular imports
                from payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary import (
                    get_summary,
                )
                
                # Get parent document and recalculate YTD
                summary = get_summary(self.parent_field_employee, self.parent_field_year)
                summary.calculate_ytd_totals()
                
                # Save with proper flags
                summary.flags.ignore_permissions = True
                summary.flags.ignore_validate_update_after_submit = True
                summary.save()
        except Exception as e:
            logger.exception(f"Error updating parent from monthly detail {self.name}: {str(e)}")


def upsert_monthly_detail(slip: Document) -> Optional[Document]:
    """
    Create or update a monthly tax detail record from a salary slip.
    
    This function takes a Salary Slip document and either creates a new monthly
    detail record or updates an existing one with the tax-related information
    from the slip.
    
    Args:
        slip: The Salary Slip document to extract data from
        
    Returns:
        Optional[Document]: The updated monthly detail document, or None on error
    """
    try:
        # Validate input
        if not slip or not hasattr(slip, "employee") or not slip.employee:
            logger.error("Invalid salary slip provided to upsert_monthly_detail")
            return None
        
        # Determine month and year
        month = _get_month_from_slip(slip)
        year = _get_year_from_slip(slip)
        
        if not month or not year:
            logger.error(f"Could not determine month/year from slip {slip.name}")
            return None
        
        # Import here to avoid circular imports
        from payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary import (
            get_summary,
        )
        
        # Get parent document
        summary = get_summary(slip.employee, year)
        
        # Find existing monthly detail or create new one
        detail = None
        for row in summary.monthly_details:
            if row.month == month:
                detail = row
                break
        
        if not detail:
            detail = summary.append("monthly_details", {"month": month})
        
        # Extract and update values
        values = _extract_values_from_slip(slip)
        
        # Update fields
        detail.gross_pay = values["gross_pay"]
        detail.tax_amount = values["tax_amount"]
        detail.bpjs_deductions_employee = values["bpjs_deductions"]
        detail.other_deductions = values["other_deductions"]
        detail.salary_slip = slip.name
        detail.is_using_ter = values["is_using_ter"]
        detail.ter_rate = values["ter_rate"]
        
        # Update additional fields if they exist
        for field, value in values.items():
            if hasattr(detail, field) and field not in [
                "gross_pay", "tax_amount", "bpjs_deductions", "other_deductions",
                "is_using_ter", "ter_rate"
            ]:
                setattr(detail, field, value)
        
        # Save parent document
        summary.calculate_ytd_totals()
        summary.flags.ignore_permissions = True
        summary.flags.ignore_validate_update_after_submit = True
        summary.save()
        
        logger.info(
            f"Updated monthly tax detail for employee {slip.employee}, "
            f"month {month}/{year} from slip {slip.name}"
        )
        
        return detail
    
    except Exception as e:
        logger.exception(f"Error upserting monthly detail from slip {slip.name}: {str(e)}")
        return None


def clear_monthly_detail(slip_name: str) -> bool:
    """
    Clear monthly tax detail data when a salary slip is cancelled.
    
    Args:
        slip_name: Name of the cancelled salary slip
        
    Returns:
        bool: True if data was cleared, False otherwise
    """
    try:
        # Get the salary slip
        slip = frappe.get_doc("Salary Slip", slip_name)
        
        if not slip or not hasattr(slip, "employee") or not slip.employee:
            logger.error(f"Invalid salary slip {slip_name}")
            return False
        
        # Verify slip is cancelled
        if slip.docstatus != 2:  # 2 = Cancelled
            logger.warning(
                f"Salary slip {slip_name} is not cancelled (status={slip.docstatus}), "
                "skipping tax detail clear"
            )
            return False
        
        # Determine month and year
        month = _get_month_from_slip(slip)
        year = _get_year_from_slip(slip)
        
        if not month or not year:
            logger.error(f"Could not determine month/year from slip {slip_name}")
            return False
        
        # Find the tax summary
        summary_name = frappe.db.get_value(
            "Employee Tax Summary",
            {"employee": slip.employee, "year": year}
        )
        
        if not summary_name:
            logger.info(f"No tax summary found for employee {slip.employee}, year {year}")
            return False
        
        # Find the monthly detail
        detail_name = frappe.db.get_value(
            "Employee Monthly Tax Detail",
            {
                "parent": summary_name,
                "month": month,
                "salary_slip": slip_name
            }
        )
        
        if not detail_name:
            logger.info(
                f"No monthly detail found for slip {slip_name} in "
                f"month {month}/{year}"
            )
            return False
        
        # Get the monthly detail
        detail = frappe.get_doc("Employee Monthly Tax Detail", detail_name)
        
        # Clear values
        detail.gross_pay = 0
        detail.tax_amount = 0
        detail.bpjs_deductions_employee = 0
        detail.other_deductions = 0
        detail.salary_slip = ""
        detail.is_using_ter = 0
        detail.ter_rate = 0
        
        # Clear additional fields if they exist
        for field in ["biaya_jabatan", "netto", "annual_taxable_income", "ter_category"]:
            if hasattr(detail, field):
                if field == "ter_category":
                    detail.ter_category = ""
                else:
                    setattr(detail, field, 0)
        
        # Save the detail
        detail.flags.ignore_permissions = True
        detail.save()
        
        # Update parent document
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
        summary.calculate_ytd_totals()
        summary.flags.ignore_permissions = True
        summary.flags.ignore_validate_update_after_submit = True
        summary.save()
        
        logger.info(
            f"Cleared monthly tax detail for employee {slip.employee}, "
            f"month {month}/{year} from slip {slip_name}"
        )
        
        return True
    
    except Exception as e:
        logger.exception(f"Error clearing monthly detail for slip {slip_name}: {str(e)}")
        return False


def _extract_values_from_slip(slip: Document) -> Dict[str, Any]:
    """
    Extract tax-related values from a salary slip.
    
    Args:
        slip: Salary Slip document
        
    Returns:
        Dict: Dictionary containing extracted values
    """
    # Initialize with defaults
    values = {
        "gross_pay": 0,
        "tax_amount": 0,
        "bpjs_deductions": 0,
        "other_deductions": 0,
        "is_using_ter": 0,
        "ter_rate": 0,
        "ter_category": "",
        "biaya_jabatan": 0,
        "netto": 0
    }
    
    # Get gross pay
    if hasattr(slip, "gross_pay"):
        values["gross_pay"] = flt(slip.gross_pay)
    
    # Extract deduction values
    if hasattr(slip, "deductions"):
        for deduction in slip.deductions:
            if deduction.salary_component == "PPh 21":
                values["tax_amount"] = flt(deduction.amount)
            elif deduction.salary_component in [
                "BPJS JHT Employee",
                "BPJS JP Employee",
                "BPJS Kesehatan Employee"
            ]:
                values["bpjs_deductions"] += flt(deduction.amount)
            else:
                values["other_deductions"] += flt(deduction.amount)
    
    # Get TER information
    if hasattr(slip, "is_using_ter"):
        values["is_using_ter"] = cint(slip.is_using_ter)
    
    if hasattr(slip, "ter_rate"):
        values["ter_rate"] = flt(slip.ter_rate)
    
    if hasattr(slip, "ter_category"):
        values["ter_category"] = slip.ter_category
    
    # Get additional calculation fields
    for field in ["biaya_jabatan", "netto"]:
        if hasattr(slip, field):
            values[field] = flt(getattr(slip, field))
    
    return values


def _get_month_from_slip(slip: Document) -> Optional[int]:
    """
    Determine the month from a salary slip.
    
    Args:
        slip: Salary Slip document
        
    Returns:
        Optional[int]: Month number (1-12) or None if not found
    """
    if hasattr(slip, "start_date") and slip.start_date:
        return getdate(slip.start_date).month
    
    if hasattr(slip, "posting_date") and slip.posting_date:
        return getdate(slip.posting_date).month
    
    return None


def _get_year_from_slip(slip: Document) -> Optional[int]:
    """
    Determine the year from a salary slip.
    
    Args:
        slip: Salary Slip document
        
    Returns:
        Optional[int]: Year or None if not found
    """
    if hasattr(slip, "start_date") and slip.start_date:
        return getdate(slip.start_date).year
    
    if hasattr(slip, "posting_date") and slip.posting_date:
        return getdate(slip.posting_date).year
    
    return None


@frappe.whitelist()
def get_tax_detail(slip_name: str) -> Dict[str, Any]:
    """
    Get the tax detail information for a specific salary slip.
    
    Args:
        slip_name: Name of the salary slip
        
    Returns:
        Dict: Tax detail information
    """
    try:
        # Get the salary slip
        slip = frappe.get_doc("Salary Slip", slip_name)
        
        if not slip or not slip.employee:
            return {"status": "error", "message": "Invalid salary slip"}
        
        # Determine month and year
        month = _get_month_from_slip(slip)
        year = _get_year_from_slip(slip)
        
        if not month or not year:
            return {"status": "error", "message": "Could not determine month/year"}
        
        # Find the tax summary
        summary_name = frappe.db.get_value(
            "Employee Tax Summary",
            {"employee": slip.employee, "year": year}
        )
        
        if not summary_name:
            return {
                "status": "error", 
                "message": f"No tax summary found for {slip.employee} in {year}"
            }
        
        # Find the monthly detail
        detail = frappe.db.get_value(
            "Employee Monthly Tax Detail",
            {"parent": summary_name, "month": month},
            [
                "gross_pay", "tax_amount", "bpjs_deductions_employee",
                "other_deductions", "is_using_ter", "ter_rate", "name"
            ],
            as_dict=True
        )
        
        if not detail:
            return {
                "status": "error",
                "message": f"No tax detail found for month {month}/{year}"
            }
        
        # Return the detail information
        return {
            "status": "success",
            "employee": slip.employee,
            "month": month,
            "year": year,
            "gross_pay": detail.gross_pay,
            "tax_amount": detail.tax_amount,
            "bpjs_deductions": detail.bpjs_deductions_employee,
            "other_deductions": detail.other_deductions,
            "is_using_ter": detail.is_using_ter,
            "ter_rate": detail.ter_rate,
            "detail_name": detail.name,
            "summary_name": summary_name
        }
    
    except Exception as e:
        logger.exception(f"Error getting tax detail for slip {slip_name}: {str(e)}")
        return {"status": "error", "message": str(e)}