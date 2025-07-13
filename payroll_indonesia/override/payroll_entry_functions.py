# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:36:51 by dannyaudian

"""
Helper functions for Payroll Entry processing.

This module provides utility functions for Indonesian payroll entry processing,
including salary slip creation, submission, and employer contribution calculations.
"""

from typing import Any, Dict, List, Tuple, Optional

import frappe
from frappe import _
from frappe.utils import getdate, date_diff, flt

from payroll_indonesia.config.config import get_live_config
import payroll_indonesia.override.salary_slip.bpjs_calculator as bpjs_calc
import payroll_indonesia.override.salary_slip.tax_calculator as tax_calc
import payroll_indonesia.payroll_indonesia.validations as validations
from payroll_indonesia.frappe_helpers import logger

__all__ = [
    "is_december_calculation",
    "calculate_payment_days",
    "create_salary_slip",
    "make_slips_from_timesheets",
    "submit_salary_slips",
    "post_submit",
    "calculate_employer_contributions",
    "auto_sync_december_flags", # Add new function to exports
]


def is_december_calculation(entry: Any) -> bool:
    """Return ``True`` if December override flag is enabled on the entry."""

    return bool(getattr(entry, "is_december_override", 0))


def auto_sync_december_flags(doc: Any) -> bool:
    """
    Auto-detect December from end_date and synchronize December-related flags.
    
    This utility function provides centralized logic for:
    1. Detecting December month from end_date
    2. Setting is_december_override and run_as_december flags consistently
    3. Synchronizing the flags when one is set but not the other
    
    Can be used in both Payroll Entry and Salary Slip documents.
    
    Args:
        doc: Document with end_date and December flags (Payroll Entry or Salary Slip)
        
    Returns:
        bool: True if December flags were set or synced, False otherwise
    """
    changes_made = False
    
    # Initialize flags if they don't exist
    if not hasattr(doc, "is_december_override"):
        doc.is_december_override = 0
        changes_made = True
    
    if not hasattr(doc, "run_as_december"):
        doc.run_as_december = 0
        changes_made = True
    
    # Check if either flag is already set - if so, sync the other flag
    if doc.is_december_override and not doc.run_as_december:
        doc.run_as_december = 1
        logger.debug(
            f"Synced run_as_december=1 to match is_december_override for {doc.doctype} {getattr(doc, 'name', 'new')}"
        )
        changes_made = True
    elif doc.run_as_december and not doc.is_december_override:
        doc.is_december_override = 1
        logger.debug(
            f"Synced is_december_override=1 to match run_as_december for {doc.doctype} {getattr(doc, 'name', 'new')}"
        )
        changes_made = True
    
    # Skip end_date check if flags are already set
    if doc.is_december_override:
        return changes_made
    
    # Auto-detect December from end_date
    if hasattr(doc, "end_date") and doc.end_date:
        try:
            end_month = getdate(doc.end_date).month
            if end_month == 12:
                # Set both December flags
                doc.is_december_override = 1
                doc.run_as_december = 1
                
                logger.info(
                    f"Auto-detected December from end_date {doc.end_date} for {doc.doctype} {getattr(doc, 'name', 'new')} - "
                    f"setting is_december_override=1 and run_as_december=1"
                )
                
                changes_made = True
        except Exception as e:
            logger.warning(
                f"Error checking December from end_date for {doc.doctype} {getattr(doc, 'name', 'new')}: {str(e)}"
            )
    
    return changes_made


def calculate_payment_days(
    start_date: str,
    end_date: str,
    joining_date: Optional[str] = None,
    relieving_date: Optional[str] = None,
    exclude_days: int = 0,
) -> float:
    """
    Calculate payment days based on joining and relieving dates.

    Args:
        start_date: Payroll period start date
        end_date: Payroll period end date
        joining_date: Employee joining date
        relieving_date: Employee relieving date
        exclude_days: Days to exclude

    Returns:
        float: Payment days
    """
    # Convert to date objects
    start = getdate(start_date)
    end = getdate(end_date)

    # Adjust start date if employee joined after payroll start date
    if joining_date:
        joining = getdate(joining_date)
        if joining > start:
            start = joining

    # Adjust end date if employee relieved before payroll end date
    if relieving_date:
        relieving = getdate(relieving_date)
        if relieving < end:
            end = relieving

    # Calculate payment days
    payment_days = date_diff(end, start) + 1 - exclude_days
    return max(0, payment_days)


def create_salary_slip(employee_data: Dict[str, Any], entry: Any) -> str:
    """
    Create a salary slip for a single employee.

    Args:
        employee_data: Employee details dictionary
        entry: Payroll Entry document

    Returns:
        str: Name of created salary slip
    """
    # Check for existing salary slip
    existing_slip = frappe.db.exists(
        "Salary Slip",
        {
            "docstatus": ["!=", 2],  # Not cancelled
            "employee": employee_data.get("employee"),
            "start_date": entry.start_date,
            "end_date": entry.end_date,
            "company": entry.company,
        },
    )

    if existing_slip:
        logger.info(f"Salary slip already exists for {employee_data.get('employee')}")
        return existing_slip

    # Get employee details
    employee_doc = frappe.get_doc("Employee", employee_data.get("employee"))

    # Find active salary structure
    salary_structure = None

    # Query for salary structure assignment
    structure = frappe.db.sql(
        """
        SELECT sa.salary_structure
        FROM `tabSalary Structure Assignment` sa
        JOIN `tabSalary Structure` ss ON sa.salary_structure = ss.name
        WHERE sa.employee = %s
        AND sa.docstatus = 1
        AND %s BETWEEN sa.from_date AND IFNULL(sa.to_date, '2199-12-31')
        AND ss.docstatus = 1
        AND ss.is_active = 'Yes'
        AND ss.company = %s
        AND IFNULL(ss.payroll_frequency, '') = %s
        """,
        (employee_data.get("employee"), entry.posting_date, entry.company, entry.payroll_frequency),
        as_dict=True,
    )

    if structure:
        salary_structure = structure[0].salary_structure

    # Create new salary slip
    slip = frappe.new_doc("Salary Slip")
    slip.salary_slip_based_on_timesheet = getattr(entry, "salary_slip_based_on_timesheet", 0)
    slip.payroll_frequency = entry.payroll_frequency
    slip.start_date = entry.start_date
    slip.end_date = entry.end_date
    slip.employee = employee_data.get("employee")
    slip.employee_name = employee_data.get("employee_name")
    slip.company = entry.company
    slip.posting_date = entry.posting_date
    slip.payroll_entry = entry.name

    # Set salary structure if found
    if salary_structure:
        slip.salary_structure = salary_structure

    # Override automatic tax fields
    if hasattr(slip, "tax_calculation_method"):
        slip.tax_calculation_method = "Manual"
    if hasattr(slip, "income_tax_slab"):
        slip.income_tax_slab = None

    # Set December override flags - use synced flags from entry
    if hasattr(entry, "is_december_override") and entry.is_december_override:
        slip.is_december_override = 1
        slip.run_as_december = 1
    else:
        # Check if the slip itself should be December based on its end_date
        auto_sync_december_flags(slip)

    # Add department and designation if available
    if "department" in employee_data:
        slip.department = employee_data.get("department")
    if "designation" in employee_data:
        slip.designation = employee_data.get("designation")

    # Calculate payment days
    joining_date = getattr(employee_doc, "date_of_joining", None)
    relieving_date = getattr(employee_doc, "relieving_date", None)
    exclude_days = getattr(entry, "exclude_from_total_working_days", 0)

    slip.payment_days = calculate_payment_days(
        entry.start_date, entry.end_date, joining_date, relieving_date, exclude_days
    )

    # Save the slip
    slip.insert()
    logger.info(f"Created salary slip {slip.name} for {slip.employee}")

    return slip.name


def make_slips_from_timesheets(entry: Any) -> List[str]:
    """
    Create salary slips from timesheet data.

    Args:
        entry: Payroll Entry document

    Returns:
        List[str]: List of created salary slip names
    """
    if not getattr(entry, "salary_slip_based_on_timesheet", 0):
        logger.info("Payroll entry not based on timesheets, skipping")
        return []

    # Ensure December flags are synced on the entry
    auto_sync_december_flags(entry)

    # Get employees with timesheets in the period
    employees = frappe.db.sql(
        """
        SELECT DISTINCT employee, employee_name
        FROM `tabTimesheet`
        WHERE docstatus = 1
        AND start_date >= %s
        AND end_date <= %s
        AND company = %s
        AND (salary_slip IS NULL OR salary_slip = '')
        """,
        (entry.start_date, entry.end_date, entry.company),
        as_dict=True,
    )

    if not employees:
        logger.info("No employees with timesheets found for the period")
        return []

    created_slips = []

    # Create salary slips for each employee
    for emp in employees:
        try:
            # Create salary slip
            slip_name = create_salary_slip(emp, entry)
            if slip_name:
                created_slips.append(slip_name)

                # Update the timesheet to link to the salary slip
                frappe.db.sql(
                    """
                    UPDATE `tabTimesheet`
                    SET salary_slip = %s
                    WHERE docstatus = 1
                    AND start_date >= %s
                    AND end_date <= %s
                    AND company = %s
                    AND employee = %s
                    AND (salary_slip IS NULL OR salary_slip = '')
                    """,
                    (slip_name, entry.start_date, entry.end_date, entry.company, emp.employee),
                )

                frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            logger.exception(f"Error creating slip for {emp.employee}: {e}")

    return created_slips


def submit_salary_slips(slip_names: List[str]) -> Tuple[List[str], List[str]]:
    """
    Submit the specified salary slips after validation.

    Args:
        slip_names: List of salary slip names to submit

    Returns:
        Tuple[List[str], List[str]]: Submitted and failed slip names
    """
    submitted = []
    failed = []

    for slip_name in slip_names:
        try:
            slip = frappe.get_doc("Salary Slip", slip_name)

            # Don't submit if net pay is negative
            if getattr(slip, "net_pay", 0) < 0:
                logger.warning(f"Slip {slip_name} has negative net pay, skipping")
                failed.append(slip_name)
                continue

            # Submit the slip
            slip.submit()
            submitted.append(slip_name)
            logger.info(f"Submitted salary slip {slip_name}")

            frappe.db.commit()
        except frappe.DoesNotExistError:
            frappe.db.rollback()
            logger.error("Salary Slip %s not found", slip_name)
            failed.append(slip_name)
        except frappe.ValidationError as e:
            frappe.db.rollback()
            logger.error("Validation error for %s: %s", slip_name, e)
            failed.append(slip_name)
        except Exception as e:
            frappe.db.rollback()
            logger.exception(f"Error submitting slip {slip_name}: {e}")
            failed.append(slip_name)

    return submitted, failed


def post_submit(entry: Any) -> Dict[str, Any]:
    """
    Process payroll entry after submission.

    Args:
        entry: Payroll Entry document

    Returns:
        Dict[str, Any]: Result summary
    """
    # Ensure December flags are properly synced
    auto_sync_december_flags(entry)
    
    result = {"status": "success", "message": "", "submitted": 0, "failed": 0}

    try:
        # Get salary slips associated with this payroll entry
        slip_names = frappe.db.get_list(
            "Salary Slip", filters={"payroll_entry": entry.name, "docstatus": 0}, pluck="name"
        )

        if not slip_names:
            result["message"] = "No salary slips found to process"
            return result

        # Submit the salary slips
        submitted, failed = submit_salary_slips(slip_names)

        # Update result
        result["submitted"] = len(submitted)
        result["failed"] = len(failed)

        if failed:
            result["status"] = "partial"
            result["message"] = f"{len(submitted)} slips submitted, {len(failed)} failed"
        else:
            result["message"] = f"Successfully submitted {len(submitted)} salary slips"

        # Update payroll entry with submission status
        if hasattr(entry, "status"):
            if not failed:
                entry.status = "Submitted"
            else:
                entry.status = "Partially Submitted"

            entry.submitted_salary_slips = len(submitted)
            entry.failed_salary_slips = len(failed)
            entry.save(ignore_permissions=True)

        return result
    except Exception as e:
        logger.exception(f"Error in post_submit for {entry.name}: {e}")
        return {"status": "error", "message": str(e), "submitted": 0, "failed": 0}


def calculate_employer_contributions(entry: Any) -> Dict[str, float]:
    """
    Calculate total employer contributions for all salary slips.

    Args:
        entry: Payroll Entry document

    Returns:
        Dict[str, float]: Contribution amounts by type
    """
    # Get all submitted salary slips for this payroll entry
    slip_names = frappe.db.get_list(
        "Salary Slip", filters={"payroll_entry": entry.name, "docstatus": 1}, pluck="name"
    )

    if not slip_names:
        return {}

    # Initialize totals
    totals = {
        "bpjs_kesehatan": 0,
        "bpjs_jht": 0,
        "bpjs_jp": 0,
        "bpjs_jkk": 0,
        "bpjs_jkm": 0,
        "total": 0,
    }

    # Process each slip
    for slip_name in slip_names:
        slip = frappe.get_doc("Salary Slip", slip_name)

        # Calculate BPJS components
        components = bpjs_calc.calculate_components(slip)

        # Sum employer portions
        totals["bpjs_kesehatan"] += flt(components.get("kesehatan_employer", 0))
        totals["bpjs_jht"] += flt(components.get("jht_employer", 0))
        totals["bpjs_jp"] += flt(components.get("jp_employer", 0))
        totals["bpjs_jkk"] += flt(components.get("jkk", 0))
        totals["bpjs_jkm"] += flt(components.get("jkm", 0))

    # Calculate total
    totals["total"] = (
        totals["bpjs_kesehatan"]
        + totals["bpjs_jht"]
        + totals["bpjs_jp"]
        + totals["bpjs_jkk"]
        + totals["bpjs_jkm"]
    )

    return totals