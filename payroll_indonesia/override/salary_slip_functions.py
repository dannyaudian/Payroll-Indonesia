# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Functions for Salary Slip customization for Indonesian payroll.

These functions handle component updates, calculations, and post-submit operations
for salary slips, particularly focusing on tax calculations and BPJS components
for Indonesian regulations.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint, getdate
from typing import Dict, List, Optional, Any, Union, Tuple

from payroll_indonesia.frappe_helpers import get_logger

logger = get_logger("salary_slip")

from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.payroll_indonesia import utils as pi_utils
from payroll_indonesia.payroll_indonesia.utils import (
    get_ptkp_to_ter_mapping,
    get_status_pajak,
)
from payroll_indonesia.constants import BIAYA_JABATAN_PERCENT, BIAYA_JABATAN_MAX
from payroll_indonesia.override.salary_slip.tax_calculator import (
    calculate_monthly_pph_progressive,
    calculate_december_pph,
    calculate_monthly_pph_with_ter,
)

calc_bpjs = pi_utils.calculate_bpjs

EMPLOYER_COMPONENTS = (
    "BPJS Kesehatan Employer",
    "BPJS JHT Employer",
    "BPJS JP Employer",
    "BPJS JKK",
    "BPJS JKM",
)

__all__ = [
    "initialize_fields",
    "update_component_amount",
    "salary_slip_post_submit",
    "enqueue_tax_summary_update",
    "update_tax_summary",
    "update_employee_history",
]


def initialize_fields(doc: Document, method: Optional[str] = None) -> None:
    """
    Initialize custom fields on the Salary Slip document with default values.
    
    This ensures all required fields have appropriate initial values before
    calculations are performed.
    
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
        "pph21": 0,
    }

    for field, default in defaults.items():
        if not hasattr(doc, field) or getattr(doc, field) is None:
            setattr(doc, field, default)
            logger.debug(f"Initialized field {field}={default} for {doc.name}")


def update_component_amount(doc: Document, method: Optional[str] = None) -> None:
    """
    Update salary component amounts based on Indonesian tax and BPJS regulations.
    
    This is the main calculation function that updates BPJS and tax components
    in the salary slip.
    
    Args:
        doc: The Salary Slip document
        method: The method that triggered this hook (unused)
    """
    logger.debug(f"Updating component amounts for Salary Slip {doc.name}")

    # Ensure all fields are initialized
    initialize_fields(doc)

    # Get configuration
    config = get_live_config()
    bpjs_config = config.get("bpjs", {})

    # Calculate gross pay if not already set
    if not doc.gross_pay:
        doc.gross_pay = _calculate_gross_pay(doc)
        logger.debug(f"Calculated gross pay: {doc.gross_pay}")

    # Get TER information
    settings = frappe.get_cached_doc("Payroll Indonesia Settings")
    status_raw = get_status_pajak(doc)
    mapping = get_ptkp_to_ter_mapping()
    ter_category = mapping.get(status_raw, "")
    is_ter_employee = bool(ter_category)

    logger.info(
        "Tax calculation path - slip=%s, status=%s, ter_category=%s, is_ter=%s, use_ter=%s",
        doc.name,
        status_raw,
        ter_category,
        is_ter_employee,
        settings.use_ter,
    )

    try:
        # Calculate and update BPJS components
        bpjs_components = _calculate_bpjs_components(doc, bpjs_config)
        _update_bpjs_fields(doc, bpjs_components)
        _update_deduction_amounts(doc, bpjs_components, bpjs_config)

        # Initialize tax amount and correction values
        tax_amount = 0.0
        correction_amount = 0.0

        # Calculate tax amount based on method
        if settings.tax_calculation_method == "TER" and settings.use_ter and is_ter_employee:
            # TER method
            doc.is_using_ter = 1
            result = calculate_monthly_pph_with_ter(
                ter_category=ter_category,
                gross_pay=doc.gross_pay,
                slip=doc,
            )
            tax_amount = result.get("monthly_tax", 0.0)
            logger.info(f"TER method applied for {doc.name} - tax: {tax_amount}")
        else:
            # Progressive method
            doc.is_using_ter = 0
            
            # Apply year-end correction only when override flag is set
            if getattr(doc, "is_december_override", 0):
                # December annual correction calculation
                result = calculate_december_pph(doc)
                
                # Get regular monthly tax and correction amount
                monthly_tax = result.get("monthly_tax", 0.0)
                correction_amount = result.get("correction", 0.0)
                
                # Set tax amount to monthly tax (correction will be added separately)
                tax_amount = monthly_tax
                
                # Store the correction amount in the dedicated field
                doc.koreksi_pph21 = correction_amount
                
                logger.info(
                    f"December correction applied for {doc.name} - "
                    f"monthly tax: {monthly_tax}, correction: {correction_amount}, "
                    f"total: {monthly_tax + correction_amount}"
                )
                
                # Add the correction as a separate component if it exists
                if correction_amount != 0:
                    _add_or_update_correction_component(doc, correction_amount)
            else:
                # Standard monthly progressive calculation
                result = calculate_monthly_pph_progressive(doc)
                tax_amount = result.get("monthly_tax", 0.0)
                logger.info(f"Progressive method applied for {doc.name} - tax: {tax_amount}")

        # Update PPh 21 component and field
        _update_component_amount(doc, "PPh 21", tax_amount)
        doc.pph21 = tax_amount

        # Calculate biaya jabatan and netto
        biaya_jabatan = min(doc.gross_pay * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX)
        doc.biaya_jabatan = biaya_jabatan
        doc.netto = doc.gross_pay - biaya_jabatan - (doc.total_bpjs or 0)

        # Update YTD values and notes
        _update_ytd_values(doc)
        _set_payroll_note(doc)

    except Exception as e:
        logger.exception(f"Error updating component amounts for {doc.name}: {e}")

    # Update tax summary information
    update_tax_summary(doc.name)
    
    # Recalculate totals
    try:
        doc.calculate_totals()
        logger.debug(f"Component update completed for Salary Slip {doc.name}")
    except Exception as e:
        logger.exception(f"Error calculating totals for {doc.name}: {e}")


def _add_or_update_correction_component(doc: Document, correction_amount: float) -> None:
    """
    Add or update the PPh 21 Correction component in the salary slip.
    
    This function adds a separate deduction component for the annual tax correction
    in December salary slips.
    
    Args:
        doc: The Salary Slip document
        correction_amount: The correction amount to add
    """
    # Skip if no correction or deductions table doesn't exist
    if not correction_amount or not hasattr(doc, "deductions"):
        return
    
    # Look for existing correction component
    correction_component_exists = False
    for deduction in doc.deductions:
        if deduction.salary_component == "PPh 21 Correction":
            deduction.amount = correction_amount
            correction_component_exists = True
            logger.debug(f"Updated PPh 21 Correction component: {correction_amount}")
            break
    
    # Add new component if not found
    if not correction_component_exists:
        # Check if component exists in the system
        component_exists = frappe.db.exists("Salary Component", "PPh 21 Correction")
        
        if component_exists:
            # Add to deductions table
            doc.append("deductions", {
                "salary_component": "PPh 21 Correction",
                "amount": correction_amount,
                "default_amount": correction_amount,
                "additional_salary": "",
                "is_tax_applicable": 0,
                "exempted_from_income_tax": 1,
                "depends_on_payment_days": 0,
                "statistical_component": 0,
                "do_not_include_in_total": 0,
            })
            logger.debug(f"Added PPh 21 Correction component: {correction_amount}")
        else:
            logger.warning(
                "PPh 21 Correction component doesn't exist in system. "
                "Correction amount will only be stored in koreksi_pph21 field."
            )


def salary_slip_post_submit(doc: Document, method: Optional[str] = None) -> None:
    """
    Process a salary slip after it has been submitted.
    
    This function is called by the on_submit hook and handles updating
    tax summaries and other post-submission tasks.
    
    Args:
        doc: The Salary Slip document
        method: The method that triggered this hook (unused)
    """
    logger.debug(f"Processing post-submit for Salary Slip {doc.name}")

    try:
        # Ensure fields are initialized
        initialize_fields(doc)
        
        # Enqueue tax summary update
        enqueue_tax_summary_update(doc)
        
        logger.debug(f"Post-submit processing completed for Salary Slip {doc.name}")
    except Exception as e:
        logger.exception(f"Error in post-submit processing for {doc.name}: {e}")


def enqueue_tax_summary_update(doc: Document, method: Optional[str] = None) -> None:
    """
    Enqueue tax summary update to run asynchronously.
    
    This function creates a background job to update the tax summary
    after the current transaction is committed.
    
    Args:
        doc: The Salary Slip document
        method: The method that triggered this hook (unused)
    """
    try:
        if not doc or not hasattr(doc, "name") or not doc.name or not hasattr(doc, "employee") or not doc.employee:
            logger.warning(f"Cannot enqueue tax update: Invalid document or missing employee")
            return

        if method == "on_cancel":
            logger.info(f"Document {doc.name} is being cancelled, will use docstatus in update_tax_summary")
        job_name = f"tax_summary_{doc.name}_{doc.docstatus}"

        frappe.enqueue(
            "payroll_indonesia.override.salary_slip_functions.update_tax_summary",
            queue="default",
            job_name=job_name,
            enqueue_after_commit=True,
            slip_name=doc.name,
        )

        logger.info(f"Enqueued tax summary update for {doc.name} (status: {doc.docstatus}, method: {method})")
    except Exception as e:
        logger.exception(f"Failed to enqueue tax summary update for {doc.name}: {str(e)}")
        try:
            update_tax_summary(doc.name)
        except Exception as fallback_error:
            logger.exception(f"Fallback tax update also failed for {doc.name}: {str(fallback_error)}")


def update_tax_summary(slip_name: str) -> None:
    """
    Update Employee Tax Summary based on a salary slip.
    
    This function fetches the salary slip and updates or clears the 
    corresponding tax summary record based on the document status.
    
    Args:
        slip_name: Name of the Salary Slip document
    """
    try:
        # Fetch the salary slip
        slip = frappe.get_doc("Salary Slip", slip_name)
        
        # Skip processing if no employee
        if not slip.employee:
            logger.warning(f"Slip {slip_name} has no employee, skipping tax summary update")
            return
            
        logger.debug(f"Processing tax summary for {slip_name} (status: {slip.docstatus})")
        
        # Process based on document status
        _update_or_clear_tax_summary(slip)
        
    except frappe.DoesNotExistError:
        logger.error(f"Salary slip {slip_name} not found")
    except Exception as e:
        logger.exception(f"Error updating tax summary for slip {slip_name}: {str(e)}")
        frappe.log_error(
            f"Error updating tax summary for slip {slip_name}: {str(e)}",
            "Tax Summary Update Error"
        )


def _update_or_clear_tax_summary(slip: Document) -> None:
    """
    Update or clear tax summary based on slip status.
    
    This function handles both submission and cancellation cases.
    
    Args:
        slip: Salary Slip document
    """
    try:
        # Get the tax summary and detail row
        detail_row, summary = _get_or_create_tax_row(slip)
        
        if slip.docstatus == 1:  # Submitted
            # Update detail from slip
            _update_tax_detail_from_slip(detail_row, slip)
            detail_row.salary_slip = slip.name
            logger.debug(f"Updated tax detail for month {detail_row.month} from slip {slip.name}")
        elif slip.docstatus == 2:  # Cancelled
            # Clear detail values
            _zero_tax_detail(detail_row)
            detail_row.salary_slip = ""
            logger.debug(f"Cleared tax detail for month {detail_row.month} from slip {slip.name}")
        else:
            logger.warning(f"Skipping tax update for slip {slip.name} with status {slip.docstatus}")
            return
            
        # Recalculate YTD totals
        _calculate_ytd_totals(summary)
        
        # Save the tax summary
        summary.flags.ignore_permissions = True
        summary.save()
        
        logger.info(
            f"Tax summary updated for {slip.employee} - Month {detail_row.month}/{summary.year}, "
            f"docstatus={slip.docstatus}"
        )
    except Exception as e:
        logger.exception(f"Error in _update_or_clear_tax_summary for {slip.name}: {str(e)}")
        raise


def _calculate_gross_pay(doc: Document) -> float:
    """
    Calculate gross pay from earnings.
    
    Args:
        doc: Salary Slip document
        
    Returns:
        float: Total gross pay
    """
    total = 0.0

    if hasattr(doc, "earnings"):
        for earning in doc.earnings:
            total += flt(earning.amount)

    return total


def _calculate_bpjs_components(doc: Document, bpjs_config: Dict) -> Dict[str, float]:
    """
    Calculate all BPJS components.
    
    Args:
        doc: Salary Slip document
        bpjs_config: BPJS configuration dictionary
        
    Returns:
        Dict[str, float]: Dictionary of calculated BPJS component amounts
    """
    base_salary = flt(doc.gross_pay) or 0

    # Get limits from config
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


def _update_bpjs_fields(doc: Document, components: Dict[str, float]) -> None:
    """
    Update BPJS fields in the salary slip.
    
    Args:
        doc: Salary Slip document
        components: Dictionary of BPJS component amounts
    """
    doc.kesehatan_employee = components.get("kesehatan_employee", 0)
    doc.jht_employee = components.get("jht_employee", 0)
    doc.jp_employee = components.get("jp_employee", 0)
    doc.total_bpjs = components.get("total_employee", 0)

    logger.debug(f"Updated BPJS fields for {doc.name}: total_bpjs={doc.total_bpjs}")


def _update_deduction_amounts(doc: Document, components: Dict[str, float], bpjs_config: Dict) -> None:
    """
    Update deduction amounts in the salary slip.
    
    Args:
        doc: Salary Slip document
        components: Dictionary of BPJS component amounts
        bpjs_config: BPJS configuration dictionary
    """
    if not hasattr(doc, "deductions"):
        logger.warning(f"No deductions found in {doc.name}")
        return

    for deduction in doc.deductions:
        component_name = deduction.salary_component

        if component_name == "BPJS Kesehatan Employee":
            deduction.amount = components.get("kesehatan_employee", 0)
        elif component_name == "BPJS JHT Employee":
            deduction.amount = components.get("jht_employee", 0)
        elif component_name == "BPJS JP Employee":
            deduction.amount = components.get("jp_employee", 0)
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


def _update_ytd_values(doc: Document) -> None:
    """
    Update year-to-date values in the salary slip.
    
    Args:
        doc: Salary Slip document
    """
    try:
        if not doc.employee or not doc.posting_date:
            return

        year = getdate(doc.posting_date).year

        # Query for YTD totals excluding current slip
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


def _set_payroll_note(doc: Document) -> None:
    """
    Set appropriate payroll note in the salary slip.
    
    Args:
        doc: Salary Slip document
    """
    notes = []

    # Add TER note if using TER
    if getattr(doc, "is_using_ter", 0):
        notes.append(f"Perhitungan pajak menggunakan metode TER ({getattr(doc, 'ter_rate', 0)}%)")

    # Add December note if December override
    if getattr(doc, "is_december_override", 0):
        notes.append("Slip ini menggunakan perhitungan koreksi pajak akhir tahun (Desember)")
        
        # Add correction amount if it exists
        correction = getattr(doc, "koreksi_pph21", 0)
        if correction != 0:
            notes.append(f"Jumlah koreksi PPh 21: {correction:,.2f}")

    # Set note if we have any
    if notes:
        doc.payroll_note = "\n".join(notes)
        logger.debug(f"Set payroll note for {doc.name}")


def _update_component_amount(doc: Document, component_name: str, amount: float) -> None:
    """
    Update the amount of a salary component in deductions.
    
    Args:
        doc: Salary Slip document
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


def _get_or_create_tax_row(slip: Document) -> Tuple[Any, Any]:
    """
    Get or create a tax summary row for the salary slip.
    
    Args:
        slip: Salary Slip document
        
    Returns:
        Tuple containing (monthly detail row, parent tax summary)
    """
    # Determine year
    if hasattr(slip, "start_date") and slip.start_date:
        year = getdate(slip.start_date).year
    else:
        year = getdate(slip.posting_date).year

    # Find or create tax summary
    filters = {"employee": slip.employee, "year": year}
    summary_name = frappe.db.get_value("Employee Tax Summary", filters)

    if summary_name:
        summary = frappe.get_doc("Employee Tax Summary", summary_name)
    else:
        # Create new summary
        summary = frappe.new_doc("Employee Tax Summary")
        summary.employee = slip.employee
        summary.year = year
        summary.insert(ignore_permissions=True)

    # Determine month
    if hasattr(slip, "start_date") and slip.start_date:
        month = getdate(slip.start_date).month
    else:
        month = getdate(slip.posting_date).month

    # Find or create monthly detail
    row = None
    for detail in summary.get("monthly_details", []):
        if detail.month == month:
            row = detail
            break

    if not row:
        # Create new monthly detail
        row = summary.append(
            "monthly_details",
            {
                "month": month,
                "gross_pay": 0,
                "tax_amount": 0,
                "bpjs_deductions_employee": 0,
                "other_deductions": 0,
                "salary_slip": "",
                "is_using_ter": 0,
                "ter_rate": 0,
            },
        )

    return row, summary


def _update_tax_detail_from_slip(row: Any, slip: Document) -> None:
    """
    Update tax detail row with values from salary slip.
    
    Args:
        row: Monthly tax detail row
        slip: Salary Slip document
    """
    # Initialize values
    tax_amount = 0
    bpjs_deductions = 0
    other_deductions = 0

    # Extract values from deductions
    if hasattr(slip, "deductions"):
        for deduction in slip.deductions:
            if deduction.salary_component == "PPh 21":
                tax_amount = flt(deduction.amount)
            elif deduction.salary_component == "PPh 21 Correction":
                # If there's a correction component, add it to the tax amount
                tax_amount += flt(deduction.amount)
            elif deduction.salary_component in [
                "BPJS JHT Employee",
                "BPJS JP Employee",
                "BPJS Kesehatan Employee",
            ]:
                bpjs_deductions += flt(deduction.amount)
            else:
                other_deductions += flt(deduction.amount)

    # Update basic fields
    row.gross_pay = flt(getattr(slip, "gross_pay", 0))
    row.tax_amount = tax_amount

    # Update fields that might have different names
    if hasattr(row, "bpjs_deductions"):
        row.bpjs_deductions = bpjs_deductions
    if hasattr(row, "bpjs_deductions_employee"):
        row.bpjs_deductions_employee = bpjs_deductions
    if hasattr(row, "other_deductions"):
        row.other_deductions = other_deductions

    # Update TER information
    if hasattr(row, "is_using_ter") and hasattr(slip, "is_using_ter"):
        row.is_using_ter = cint(slip.is_using_ter)
    if hasattr(row, "ter_rate") and hasattr(slip, "ter_rate"):
        row.ter_rate = flt(slip.ter_rate)
        
    # Update correction information if field exists
    if hasattr(row, "tax_correction") and hasattr(slip, "koreksi_pph21"):
        row.tax_correction = flt(slip.koreksi_pph21)


def _zero_tax_detail(row: Any) -> None:
    """
    Reset all values in a tax detail row to zero.
    
    Args:
        row: Monthly tax detail row
    """
    # Reset basic fields
    row.gross_pay = 0
    row.tax_amount = 0

    # Reset optional fields
    if hasattr(row, "bpjs_deductions"):
        row.bpjs_deductions = 0
    if hasattr(row, "bpjs_deductions_employee"):
        row.bpjs_deductions_employee = 0
    if hasattr(row, "other_deductions"):
        row.other_deductions = 0
    if hasattr(row, "is_using_ter"):
        row.is_using_ter = 0
    if hasattr(row, "ter_rate"):
        row.ter_rate = 0
    if hasattr(row, "tax_correction"):
        row.tax_correction = 0


def _calculate_ytd_totals(summary: Document) -> None:
    """
    Calculate year-to-date totals from monthly details.
    
    Args:
        summary: Employee Tax Summary document
    """
    # Initialize totals
    ytd_totals = {
        "gross_pay": 0,
        "tax_amount": 0,
        "bpjs_deductions": 0,
        "other_deductions": 0,
        "tax_correction": 0,
    }

    # Sum up monthly details
    for detail in summary.get("monthly_details", []):
        ytd_totals["gross_pay"] += flt(detail.gross_pay)
        ytd_totals["tax_amount"] += flt(detail.tax_amount)

        # Handle different field names for BPJS
        if hasattr(detail, "bpjs_deductions_employee"):
            ytd_totals["bpjs_deductions"] += flt(detail.bpjs_deductions_employee)
        elif hasattr(detail, "bpjs_deductions"):
            ytd_totals["bpjs_deductions"] += flt(detail.bpjs_deductions)

        # Handle other deductions
        if hasattr(detail, "other_deductions"):
            ytd_totals["other_deductions"] += flt(detail.other_deductions)
            
        # Handle tax correction
        if hasattr(detail, "tax_correction"):
            ytd_totals["tax_correction"] += flt(detail.tax_correction)

    # Update summary fields
    if hasattr(summary, "ytd_gross_pay"):
        summary.ytd_gross_pay = ytd_totals["gross_pay"]
    if hasattr(summary, "ytd_tax"):
        summary.ytd_tax = ytd_totals["tax_amount"]
    if hasattr(summary, "ytd_bpjs"):
        summary.ytd_bpjs = ytd_totals["bpjs_deductions"]
    if hasattr(summary, "ytd_other_deductions"):
        summary.ytd_other_deductions = ytd_totals["other_deductions"]
    if hasattr(summary, "ytd_tax_correction"):
        summary.ytd_tax_correction = ytd_totals["tax_correction"]
    
    # Update total tax with correction if the field exists
    if hasattr(summary, "ytd_tax_with_correction"):
        summary.ytd_tax_with_correction = ytd_totals["tax_amount"] + ytd_totals["tax_correction"]


# Alias for backward compatibility
update_employee_history = update_tax_summary
