# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Functions for Salary Slip customization for Indonesian payroll.

These functions handle component updates, calculations, and post-submit operations.
"""

from typing import Dict, List, Optional, Any, Union

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate

from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.payroll_indonesia.utils import calculate_bpjs

# Define public API
__all__ = [
    "update_component_amount",
    "initialize_fields",
    "salary_slip_post_submit",
    "calculate_monthly_pro_rata",
    "calculate_tax_amount",
    "calculate_employer_contributions",
    "get_salary_components_from_structure",
]


def initialize_fields(doc, method: Optional[str] = None) -> None:
    """Ensure custom Salary Slip fields are initialized with defaults."""
    defaults = {
        "biaya_jabatan": 0,
        "netto": 0,
        "total_bpjs": 0,
        "is_using_ter": 0,
        "ter_rate": 0,
        "koreksi_pph21": 0,
    }

    for field, default in defaults.items():
        if not hasattr(doc, field) or getattr(doc, field) is None:
            setattr(doc, field, default)


def update_component_amount(doc, method: Optional[str] = None) -> None:
    """
    Update salary component amounts based on Indonesian tax and BPJS regulations.

    This function handles all special component calculations for both earnings and deductions.
    Designed to be used as a doc event hook in Salary Slip.

    Args:
        doc: The Salary Slip document
        method: The method that triggered this hook (unused)
    """
    logger.debug(f"Updating component amounts for Salary Slip {doc.name}")

    # Get configuration
    config = get_live_config()
    bpjs_config = config.get("bpjs", {})

    # Process earnings
    for earning in doc.earnings:
        # Special handling for specific earnings
        # (Add code here if needed for specific earnings)
        pass

    # Process deductions
    for deduction in doc.deductions:
        # Calculate BPJS deductions
        component_name = deduction.salary_component

        # Handle BPJS Kesehatan Employee
        if component_name == "BPJS Kesehatan Employee" and bpjs_config:
            bpjs_amount = calculate_bpjs(
                doc.gross_pay,
                bpjs_config.get("kesehatan_employee_percent", 1.0),
                bpjs_config.get("kesehatan_max_salary", 12000000),
            )
            deduction.amount = bpjs_amount
            logger.debug(f"Updated BPJS Kesehatan Employee: {bpjs_amount}")

        # Handle BPJS JHT Employee
        elif component_name == "BPJS JHT Employee" and bpjs_config:
            bpjs_amount = calculate_bpjs(
                doc.gross_pay, bpjs_config.get("jht_employee_percent", 2.0)
            )
            deduction.amount = bpjs_amount
            logger.debug(f"Updated BPJS JHT Employee: {bpjs_amount}")

        # Handle BPJS JP Employee
        elif component_name == "BPJS JP Employee" and bpjs_config:
            bpjs_amount = calculate_bpjs(
                doc.gross_pay,
                bpjs_config.get("jp_employee_percent", 1.0),
                bpjs_config.get("jp_max_salary", 9077600),
            )
            deduction.amount = bpjs_amount
            logger.debug(f"Updated BPJS JP Employee: {bpjs_amount}")

    # Update totals after modifying components
    doc.calculate_totals()

    # Calculate tax if applicable (PPh 21)
    calculate_tax_amount(doc)

    # Final recalculation
    doc.calculate_totals()
    logger.debug(f"Component update completed for Salary Slip {doc.name}")


def salary_slip_post_submit(doc, method: Optional[str] = None) -> None:
    """
    Process salary slip after submission.

    Creates necessary accounting entries and updates employee records.

    Args:
        doc: The Salary Slip document
        method: The method that triggered this hook (unused)
    """
    logger.debug(f"Processing post-submit for Salary Slip {doc.name}")

    # Update employee historical data
    update_employee_history(doc)

    # Calculate and store employer contributions
    contributions = calculate_employer_contributions(doc)
    if contributions:
        store_employer_contributions(doc, contributions)

    logger.debug(f"Post-submit processing completed for Salary Slip {doc.name}")


def calculate_monthly_pro_rata(doc) -> float:
    """
    Calculate pro-rata factor for partial month work.

    Args:
        doc: The Salary Slip document

    Returns:
        float: Pro-rata factor (0.0-1.0)
    """
    if not doc.start_date or not doc.end_date:
        return 1.0

    # Get working days info
    total_working_days = cint(doc.total_working_days) or 22
    payment_days = flt(doc.payment_days) or total_working_days

    # Calculate pro-rata factor
    pro_rata = min(1.0, max(0.0, payment_days / total_working_days))

    logger.debug(f"Calculated pro-rata factor: {pro_rata} for Salary Slip {doc.name}")
    return pro_rata


def calculate_tax_amount(doc) -> float:
    """
    Calculate PPh 21 tax amount.

    Args:
        doc: The Salary Slip document

    Returns:
        float: Calculated tax amount
    """
    # Get configuration
    config = get_live_config()
    tax_config = config.get("tax", {})

    # Basic validation
    if not tax_config:
        logger.warning("Tax configuration not found")
        return 0.0

    # Find PPh 21 component
    pph21_component = None
    for deduction in doc.deductions:
        if deduction.salary_component == "PPh 21":
            pph21_component = deduction
            break

    if not pph21_component:
        logger.debug(f"PPh 21 component not found in Salary Slip {doc.name}")
        return 0.0

    # Placeholder for actual tax calculation
    # In a real implementation, this would call the appropriate tax calculation function
    tax_amount = 0.0

    # Update component
    pph21_component.amount = tax_amount

    logger.debug(f"Calculated tax amount: {tax_amount} for Salary Slip {doc.name}")
    return tax_amount


def calculate_employer_contributions(doc) -> Dict[str, float]:
    """
    Calculate employer BPJS contributions.

    Args:
        doc: The Salary Slip document

    Returns:
        Dict[str, float]: Employer contribution amounts by component
    """
    # Get configuration
    config = get_live_config()
    bpjs_config = config.get("bpjs", {})

    if not bpjs_config:
        logger.warning("BPJS configuration not found")
        return {}

    contributions = {}
    base_salary = doc.gross_pay or 0

    # Calculate BPJS Kesehatan Employer
    contributions["BPJS Kesehatan Employer"] = calculate_bpjs(
        base_salary,
        bpjs_config.get("kesehatan_employer_percent", 4.0),
        bpjs_config.get("kesehatan_max_salary", 12000000),
    )

    # Calculate BPJS JHT Employer
    contributions["BPJS JHT Employer"] = calculate_bpjs(
        base_salary, bpjs_config.get("jht_employer_percent", 3.7)
    )

    # Calculate BPJS JP Employer
    contributions["BPJS JP Employer"] = calculate_bpjs(
        base_salary,
        bpjs_config.get("jp_employer_percent", 2.0),
        bpjs_config.get("jp_max_salary", 9077600),
    )

    # Calculate BPJS JKK
    contributions["BPJS JKK"] = calculate_bpjs(base_salary, bpjs_config.get("jkk_percent", 0.24))

    # Calculate BPJS JKM
    contributions["BPJS JKM"] = calculate_bpjs(base_salary, bpjs_config.get("jkm_percent", 0.3))

    # Calculate total
    contributions["total"] = sum(amount for key, amount in contributions.items() if key != "total")

    logger.debug(f"Calculated employer contributions: {contributions}")
    return contributions


def get_salary_components_from_structure(structure_name: str) -> Dict[str, List[Dict]]:
    """
    Get salary components from a salary structure.

    Args:
        structure_name: Name of the salary structure

    Returns:
        Dict[str, List[Dict]]: Dictionary with earnings and deductions
    """
    if not structure_name:
        return {"earnings": [], "deductions": []}

    result = {"earnings": [], "deductions": []}

    try:
        structure = frappe.get_doc("Salary Structure", structure_name)

        # Process earnings
        for earning in structure.earnings:
            result["earnings"].append(
                {
                    "salary_component": earning.salary_component,
                    "abbr": earning.abbr or "",
                    "amount": flt(earning.amount),
                    "formula": earning.formula or "",
                    "condition": earning.condition or "",
                }
            )

        # Process deductions
        for deduction in structure.deductions:
            result["deductions"].append(
                {
                    "salary_component": deduction.salary_component,
                    "abbr": deduction.abbr or "",
                    "amount": flt(deduction.amount),
                    "formula": deduction.formula or "",
                    "condition": deduction.condition or "",
                }
            )

    except Exception as e:
        logger.error(f"Error retrieving components from structure {structure_name}: {e}")

    return result


def update_employee_history(doc) -> None:
    """
    Update employee's historical salary and tax data.

    Args:
        doc: The Salary Slip document
    """
    if not doc.employee:
        return

    try:
        # Get year of salary slip
        slip_year = getdate(doc.posting_date).year

        # Get existing history or create new
        history_name = f"{doc.employee}-{slip_year}"
        if frappe.db.exists("Employee Salary History", history_name):
            history = frappe.get_doc("Employee Salary History", history_name)
        else:
            history = frappe.new_doc("Employee Salary History")
            history.employee = doc.employee
            history.year = slip_year
            history.ytd_gross = 0
            history.ytd_tax = 0

        # Update YTD amounts
        history.ytd_gross += flt(doc.gross_pay)

        # Update YTD tax if PPh 21 exists
        for deduction in doc.deductions:
            if deduction.salary_component == "PPh 21":
                history.ytd_tax += flt(deduction.amount)
                break

        # Save history
        history.flags.ignore_permissions = True
        history.save()

        logger.debug(f"Updated salary history for employee {doc.employee}")

    except Exception as e:
        logger.error(f"Error updating employee history: {e}")


def store_employer_contributions(doc, contributions: Dict[str, float]) -> None:
    """
    Store employer contributions in custom doctype.

    Args:
        doc: The Salary Slip document
        contributions: Dictionary of contribution amounts
    """
    if not contributions:
        return

    try:
        # Check if employer contribution doc exists
        existing = frappe.db.exists("Employer Contribution", {"salary_slip": doc.name})

        if existing:
            contribution_doc = frappe.get_doc("Employer Contribution", existing)
        else:
            contribution_doc = frappe.new_doc("Employer Contribution")
            contribution_doc.salary_slip = doc.name
            contribution_doc.employee = doc.employee
            contribution_doc.posting_date = doc.posting_date

        # Update contribution amounts
        for component, amount in contributions.items():
            if component != "total":
                field_name = component.lower().replace(" ", "_")
                if hasattr(contribution_doc, field_name):
                    setattr(contribution_doc, field_name, amount)

        # Set total
        contribution_doc.total_contribution = contributions.get("total", 0)

        # Save document
        contribution_doc.flags.ignore_permissions = True
        contribution_doc.save()

        logger.debug(f"Stored employer contributions for Salary Slip {doc.name}")

    except Exception as e:
        logger.error(f"Error storing employer contributions: {e}")
