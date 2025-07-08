# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Functions for Salary Slip customization for Indonesian payroll.

These functions handle component updates, calculations, and post-submit operations.
"""

from typing import Dict, List, Optional, Any, Union, Tuple

import frappe
import logging
from frappe import _
from frappe.utils import flt, cint, getdate

from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.payroll_indonesia import utils as pi_utils
from payroll_indonesia.payroll_indonesia.utils import get_ptkp_to_ter_mapping
from payroll_indonesia.constants import BIAYA_JABATAN_PERCENT, BIAYA_JABATAN_MAX
from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter
from payroll_indonesia.override.salary_slip.tax_calculator import (
    calculate_monthly_pph_progressive,
    calculate_december_pph,
)

# Set up logger
logger = logging.getLogger(__name__)

# Import calculate_bpjs function for easier reference
calc_bpjs = pi_utils.calculate_bpjs

# Define employer BPJS components
EMPLOYER_COMPONENTS = (
    "BPJS Kesehatan Employer",
    "BPJS JHT Employer",
    "BPJS JP Employer",
    "BPJS JKK",
    "BPJS JKM",
)

# Define public API
__all__ = [
    "update_tax_summary",
    "update_employee_history",  # alias
    "update_component_amount",
    "salary_slip_post_submit",
    "initialize_fields",  # Keep this to avoid import errors
]


def initialize_fields(doc, method: Optional[str] = None) -> None:
    """
    Ensure custom Salary Slip fields are initialized with defaults.

    Args:
        doc: The Salary Slip document
        method: The method that triggered this hook (unused)
    """
    defaults = {
        "biaya_jabatan": 0,
        "netto": 0,
        "total_bpjs": 0,
        "is_using_ter": 0,
        "ter_rate": 0,
        "koreksi_pph21": 0,
        "ytd_gross_pay": 0,
        "ytd_bpjs_deductions": 0,
        "kesehatan_employee": 0,
        "jht_employee": 0,
        "jp_employee": 0,
        "pph21": 0,  # Ensure PPh 21 field is initialized
    }

    for field, default in defaults.items():
        if not hasattr(doc, field) or getattr(doc, field) is None:
            setattr(doc, field, default)
            logger.debug(f"Initialized field {field}={default} for {doc.name}")


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

    # Ensure fields are initialized
    initialize_fields(doc)

    # Get configuration
    config = get_live_config()
    bpjs_config = config.get("bpjs", {})

    # Ensure gross pay is calculated
    if not doc.gross_pay:
        doc.gross_pay = _calculate_gross_pay(doc)
        logger.debug(f"Calculated gross pay: {doc.gross_pay}")

    # Determine TER eligibility
    settings = frappe.get_cached_doc("Payroll Indonesia Settings")
    mapping = get_ptkp_to_ter_mapping()
    status_raw = str(getattr(doc, "status_pajak", "")).upper()
    ter_category = mapping.get(status_raw, "")
    is_ter_employee = bool(ter_category)

    # Log key TER-related values for easier debugging of tax calculation logic
    logger.info(
        "TER debugging - settings.use_ter: %s, settings.tax_calculation_method: %s, "
        "status_pajak: %s, is_ter_employee: %s",
        settings.use_ter,
        settings.tax_calculation_method,
        status_raw,
        is_ter_employee,
    )

    # Process BPJS and tax components
    try:
        # Calculate BPJS components and update fields
        bpjs_components = _calculate_bpjs_components(doc, bpjs_config)
        _update_bpjs_fields(doc, bpjs_components)

        # Update deduction amounts
        _update_deduction_amounts(doc, bpjs_components, bpjs_config)

        # Apply tax calculation based on method
        if settings.tax_calculation_method == "TER" and settings.use_ter and is_ter_employee:
            doc.is_using_ter = 1
            result = calculate_monthly_pph_with_ter(
                ter_category=ter_category,
                gross_pay=doc.gross_pay,
                slip=doc,
            )
            tax_amount = result.get("monthly_tax", 0.0)
            logger.info(f"TER method applied for {doc.name} - tax: {tax_amount}")
        else:
            doc.is_using_ter = 0
            if getattr(doc, "is_december_override", 0):
                result = calculate_december_pph(doc)
                tax_amount = result.get("correction", 0.0)
                logger.info(f"December correction applied for {doc.name} - tax: {tax_amount}")
            else:
                result = calculate_monthly_pph_progressive(doc)
                tax_amount = result.get("monthly_tax", 0.0)
                logger.info(f"Progressive method applied for {doc.name} - tax: {tax_amount}")

        # Update PPh 21 component
        _update_component_amount(doc, "PPh 21", tax_amount)
        doc.pph21 = tax_amount

        # Calculate netto (needed for tax calculation)
        biaya_jabatan = min(doc.gross_pay * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX)
        doc.biaya_jabatan = biaya_jabatan
        doc.netto = doc.gross_pay - biaya_jabatan - (doc.total_bpjs or 0)

        # Update YTD values
        _update_ytd_values(doc)

        # Set appropriate payroll note
        _set_payroll_note(doc)

    except Exception as e:
        logger.exception(f"Error updating component amounts for {doc.name}: {e}")

    # Update tax summary
    update_tax_summary(doc)

    # Update totals after modifying components
    try:
        doc.calculate_totals()
        logger.debug(f"Component update completed for Salary Slip {doc.name}")
    except Exception as e:
        logger.exception(f"Error calculating totals for {doc.name}: {e}")


def _calculate_gross_pay(doc) -> float:
    """
    Calculate gross pay from earnings.

    Args:
        doc: The Salary Slip document

    Returns:
        float: Total gross pay
    """
    total = 0.0

    if hasattr(doc, "earnings"):
        for earning in doc.earnings:
            total += flt(earning.amount)

    return total


def _calculate_bpjs_components(doc, bpjs_config: Dict) -> Dict[str, float]:
    """
    Calculate all BPJS components.

    Args:
        doc: The Salary Slip document
        bpjs_config: BPJS configuration dictionary

    Returns:
        Dict[str, float]: Dictionary of BPJS component amounts
    """
    base_salary = flt(doc.gross_pay) or 0

    # Get limits and percentages from config or use defaults
    kesehatan_max = flt(bpjs_config.get("kesehatan_max_salary", 12000000))
    jp_max = flt(bpjs_config.get("jp_max_salary", 9077600))

    # Calculate employee components
    kesehatan_employee = calc_bpjs(
        base_salary, bpjs_config.get("kesehatan_employee_percent", 1.0), max_salary=kesehatan_max
    )

    jht_employee = calc_bpjs(base_salary, bpjs_config.get("jht_employee_percent", 2.0))

    jp_employee = calc_bpjs(
        base_salary, bpjs_config.get("jp_employee_percent", 1.0), max_salary=jp_max
    )

    # Calculate employer components
    kesehatan_employer = calc_bpjs(
        base_salary, bpjs_config.get("kesehatan_employer_percent", 4.0), max_salary=kesehatan_max
    )

    jht_employer = calc_bpjs(base_salary, bpjs_config.get("jht_employer_percent", 3.7))

    jp_employer = calc_bpjs(
        base_salary, bpjs_config.get("jp_employer_percent", 2.0), max_salary=jp_max
    )

    jkk = calc_bpjs(base_salary, bpjs_config.get("jkk_percent", 0.24))
    jkm = calc_bpjs(base_salary, bpjs_config.get("jkm_percent", 0.3))

    # Calculate totals
    total_employee = kesehatan_employee + jht_employee + jp_employee
    total_employer = kesehatan_employer + jht_employer + jp_employer + jkk + jkm

    # Return all components
    return {
        "kesehatan_employee": kesehatan_employee,
        "jht_employee": jht_employee,
        "jp_employee": jp_employee,
        "kesehatan_employer": kesehatan_employer,
        "jht_employer": jht_employer,
        "jp_employer": jp_employer,
        "jkk": jkk,
        "jkm": jkm,
        "total_employee": total_employee,
        "total_employer": total_employer,
    }


def _update_bpjs_fields(doc, components: Dict[str, float]) -> None:
    """
    Update BPJS fields in the salary slip.

    Args:
        doc: The Salary Slip document
        components: Dictionary of BPJS component amounts
    """
    # Update employee BPJS fields
    doc.kesehatan_employee = components.get("kesehatan_employee", 0)
    doc.jht_employee = components.get("jht_employee", 0)
    doc.jp_employee = components.get("jp_employee", 0)
    doc.total_bpjs = components.get("total_employee", 0)

    logger.debug(f"Updated BPJS fields for {doc.name}: total_bpjs={doc.total_bpjs}")


def _update_deduction_amounts(doc, components: Dict[str, float], bpjs_config: Dict) -> None:
    """
    Update deduction amounts in the salary slip.

    Args:
        doc: The Salary Slip document
        components: Dictionary of BPJS component amounts
        bpjs_config: BPJS configuration dictionary
    """
    if not hasattr(doc, "deductions"):
        logger.warning(f"No deductions found in {doc.name}")
        return

    for deduction in doc.deductions:
        component_name = deduction.salary_component

        # Handle BPJS Kesehatan Employee
        if component_name == "BPJS Kesehatan Employee":
            deduction.amount = components.get("kesehatan_employee", 0)
            logger.debug(f"Updated BPJS Kesehatan Employee: {deduction.amount}")

        # Handle BPJS JHT Employee
        elif component_name == "BPJS JHT Employee":
            deduction.amount = components.get("jht_employee", 0)
            logger.debug(f"Updated BPJS JHT Employee: {deduction.amount}")

        # Handle BPJS JP Employee
        elif component_name == "BPJS JP Employee":
            deduction.amount = components.get("jp_employee", 0)
            logger.debug(f"Updated BPJS JP Employee: {deduction.amount}")

        # Handle employer components for reporting
        elif component_name == "BPJS Kesehatan Employer":
            deduction.amount = components.get("kesehatan_employer", 0)
        elif component_name == "BPJS JHT Employer":
            deduction.amount = components.get("jht_employer", 0)
        elif component_name == "BPJS JP Employer":
            deduction.amount = components.get("jp_employer", 0)
        elif component_name == "BPJS JKK":
            deduction.amount = components.get("jkk", 0)
        elif component_name == "BPJS JKM":
            deduction.amount = components.get("jkm", 0)


def _update_ytd_values(doc) -> None:
    """
    Update YTD values in the salary slip.

    Args:
        doc: The Salary Slip document
    """
    try:
        if not doc.employee or not doc.posting_date:
            return

        # Get YTD values excluding current slip
        year = getdate(doc.posting_date).year

        # Query for YTD totals
        ytd_data = frappe.db.sql(
            """
            SELECT 
                SUM(gross_pay) as gross_pay,
                SUM(total_bpjs) as total_bpjs
            FROM `tabSalary Slip`
            WHERE docstatus = 1
              AND employee = %s
              AND YEAR(posting_date) = %s
              AND name != %s
            """,
            (doc.employee, year, doc.name),
            as_dict=1,
        )

        if ytd_data and len(ytd_data) > 0:
            doc.ytd_gross_pay = flt(ytd_data[0].gross_pay) or 0
            doc.ytd_bpjs_deductions = flt(ytd_data[0].total_bpjs) or 0

            logger.debug(
                f"Updated YTD values for {doc.name}: "
                f"ytd_gross={doc.ytd_gross_pay}, ytd_bpjs={doc.ytd_bpjs_deductions}"
            )

    except Exception as e:
        logger.exception(f"Error updating YTD values for {doc.name}: {e}")


def _set_payroll_note(doc) -> None:
    """
    Set appropriate payroll note in the salary slip.

    Args:
        doc: The Salary Slip document
    """
    notes = []

    # Add TER note if using TER
    if getattr(doc, "is_using_ter", 0):
        notes.append(f"Perhitungan pajak menggunakan metode TER ({getattr(doc, 'ter_rate', 0)}%)")

    # Add December note if December override
    if getattr(doc, "is_december_override", 0):
        notes.append("Slip ini menggunakan perhitungan koreksi pajak akhir tahun (Desember)")

    # Set note
    if notes:
        doc.payroll_note = "\n".join(notes)
        logger.debug(f"Set payroll note for {doc.name}")


def salary_slip_post_submit(doc, method: Optional[str] = None) -> None:
    """
    Process salary slip after submission.

    Updates employee tax summary records.

    Args:
        doc: The Salary Slip document
        method: The method that triggered this hook (unused)
    """
    logger.debug(f"Processing post-submit for Salary Slip {doc.name}")

    try:
        # Ensure fields are initialized
        initialize_fields(doc)

        # Update tax summary
        update_tax_summary(doc)

        logger.debug(f"Post-submit processing completed for Salary Slip {doc.name}")

    except Exception as e:
        logger.exception(f"Error in post-submit processing for {doc.name}: {e}")


def _update_component_amount(doc, component_name: str, amount: float) -> None:
    """
    Update the amount of a salary component in deductions.

    Args:
        doc: The Salary Slip document
        component_name: Name of the salary component
        amount: Amount to set
    """
    if not hasattr(doc, "deductions"):
        return

    for deduction in doc.deductions:
        if deduction.salary_component == component_name:
            deduction.amount = amount
            logger.debug(f"Updated {component_name}: {amount}")
            break


def _get_component_amount(doc, component_name: str) -> float:
    """
    Get the amount of a salary component from deductions.

    Args:
        doc: The Salary Slip document
        component_name: Name of the salary component

    Returns:
        float: Amount of the component, 0 if not found
    """
    if not hasattr(doc, "deductions"):
        return 0.0

    for deduction in doc.deductions:
        if deduction.salary_component == component_name:
            return flt(deduction.amount)

    return 0.0


def _get_or_create_tax_row(slip) -> Tuple[Any, Any]:
    """
    Get or create a tax summary row for the salary slip.

    Args:
        slip: The Salary Slip document

    Returns:
        Tuple containing (child row, parent doc)
    """
    # Get employee and company
    employee = slip.employee
    company = slip.company

    # Derive fiscal year from start_date if not present
    fiscal_year = getattr(slip, "fiscal_year", None)
    if not fiscal_year and hasattr(slip, "start_date"):
        fiscal_year = getdate(slip.start_date).year

    if not fiscal_year:
        fiscal_year = getdate(slip.posting_date).year

    filters = {"employee": employee, "company": company, "fiscal_year": fiscal_year}

    summary_name = frappe.db.get_value("Employee Tax Summary", filters)

    if summary_name:
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
    else:
        summary = frappe.new_doc("Employee Tax Summary")
        summary.employee = employee
        summary.company = company
        summary.fiscal_year = fiscal_year

    # Find or create the monthly detail row
    month = getattr(slip, "month", None)
    if not month and hasattr(slip, "start_date"):
        month = getdate(slip.start_date).month

    if not month:
        month = getdate(slip.posting_date).month

    row = None
    for detail in summary.monthly_details:
        if detail.month == month:
            row = detail
            break

    if not row:
        row = summary.append(
            "monthly_details",
            {"month": month, "taxable_income": 0, "tax_withheld": 0, "bpjs_employer_share": 0},
        )

    return row, summary


def update_tax_summary(slip) -> None:
    """
    Update Employee Tax Summary with salary slip data.

    Args:
        slip: The Salary Slip document
    """
    if not slip.employee or not slip.company:
        return

    try:
        # Get or create tax summary row
        row, parent = _get_or_create_tax_row(slip)

        # Update taxable income and tax withheld
        row.taxable_income = flt(slip.gross_pay) or 0
        row.tax_withheld = _get_component_amount(slip, "PPh 21")

        # Calculate employer BPJS share
        employer_share = sum(
            _get_component_amount(slip, component) for component in EMPLOYER_COMPONENTS
        )

        # Update employer share
        row.bpjs_employer_share = employer_share

        # Save the documents
        parent.save(ignore_permissions=True)

        logger.info(f"Tax summary updated for {slip.employee} - {row.month}/{parent.fiscal_year}")

    except Exception as e:
        logger.exception(f"Error updating tax summary for {slip.employee}: {e}")


# Alias for backward compatibility
update_employee_history = update_tax_summary
