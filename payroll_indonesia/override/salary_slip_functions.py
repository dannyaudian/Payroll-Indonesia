# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Functions for Salary Slip customization for Indonesian payroll.

These functions handle component updates, calculations, and post-submit operations.
"""

from typing import Dict, List, Optional, Any, Union, Tuple

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate
from frappe.utils.background_jobs import enqueue

from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.payroll_indonesia import utils as pi_utils
from payroll_indonesia.constants import BIAYA_JABATAN_PERCENT, BIAYA_JABATAN_MAX

# Import calculate_bpjs function for easier reference
calc_bpjs = pi_utils.calculate_bpjs

# Define public API
__all__ = [
    "update_component_amount",
    "initialize_fields",
    "salary_slip_post_submit",
    "calculate_monthly_pro_rata",
    "calculate_tax_amount",
    "calculate_employer_contributions",
    "get_salary_components_from_structure",
    "enqueue_tax_summary_update",
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
    
    # Ensure employee doc is available for tax calculations
    if not hasattr(doc, "employee_doc") and doc.employee:
        try:
            doc.employee_doc = frappe.get_doc("Employee", doc.employee)
            logger.debug(f"Loaded employee_doc for {doc.employee}")
        except Exception as e:
            logger.exception(f"Error loading employee doc for {doc.employee}: {e}")
            # Continue anyway, but log the issue
    
    # Set gross pay if not already set
    if not doc.gross_pay:
        doc.gross_pay = _calculate_gross_pay(doc)
        logger.debug(f"Calculated gross pay: {doc.gross_pay}")
    
    # Process BPJS and tax components
    try:
        # Calculate BPJS components and update fields
        bpjs_components = _calculate_bpjs_components(doc, bpjs_config)
        _update_bpjs_fields(doc, bpjs_components)
        
        # Update deduction amounts
        _update_deduction_amounts(doc, bpjs_components, bpjs_config)
        
        # Calculate tax and update fields
        tax_amount = calculate_tax_amount(doc)
        
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
        base_salary, 
        bpjs_config.get("kesehatan_employee_percent", 1.0),
        max_salary=kesehatan_max
    )
    
    jht_employee = calc_bpjs(
        base_salary, 
        bpjs_config.get("jht_employee_percent", 2.0)
    )
    
    jp_employee = calc_bpjs(
        base_salary,
        bpjs_config.get("jp_employee_percent", 1.0),
        max_salary=jp_max
    )
    
    # Calculate employer components
    kesehatan_employer = calc_bpjs(
        base_salary,
        bpjs_config.get("kesehatan_employer_percent", 4.0),
        max_salary=kesehatan_max
    )
    
    jht_employer = calc_bpjs(
        base_salary, 
        bpjs_config.get("jht_employer_percent", 3.7)
    )
    
    jp_employer = calc_bpjs(
        base_salary,
        bpjs_config.get("jp_employer_percent", 2.0),
        max_salary=jp_max
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
        "total_employer": total_employer
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
        
        # Handle PPh 21
        elif component_name == "PPh 21":
            # Will be updated by calculate_tax_amount later
            pass


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
            as_dict=1
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

    Creates necessary accounting entries and updates employee records.

    Args:
        doc: The Salary Slip document
        method: The method that triggered this hook (unused)
    """
    logger.debug(f"Processing post-submit for Salary Slip {doc.name}")
    
    try:
        # Ensure fields are initialized
        initialize_fields(doc)
        
        # Update employee historical data
        update_employee_history(doc)
        
        # Calculate and store employer contributions
        contributions = calculate_employer_contributions(doc)
        if contributions:
            store_employer_contributions(doc, contributions)
        
        # Enqueue tax summary update if needed
        if doc.docstatus == 1:
            enqueue_tax_summary_update(doc)
        
        logger.debug(f"Post-submit processing completed for Salary Slip {doc.name}")
    
    except Exception as e:
        logger.exception(f"Error in post-submit processing for {doc.name}: {e}")


def _needs_tax_summary_update(slip) -> bool:
    """
    Check if tax summary needs to be updated.
    
    Args:
        slip: The Salary Slip document
        
    Returns:
        bool: True if tax summary needs to be updated
    """
    # Always update if slip is submitted
    if getattr(slip, "docstatus", 0) != 1:
        return False
    
    # Check if any deductions exist
    if hasattr(slip, "deductions") and slip.deductions:
        # Check for any tax or BPJS components with amount > 0
        for deduction in slip.deductions:
            component_name = getattr(deduction, "salary_component", "")
            component_amount = flt(getattr(deduction, "amount", 0))
            
            if component_amount > 0 and component_name in [
                "PPh 21", "BPJS Kesehatan Employee", "BPJS JHT Employee", "BPJS JP Employee"
            ]:
                return True
    
    return False


def enqueue_tax_summary_update(slip) -> None:
    """
    Enqueue tax summary update for background processing.
    
    Args:
        slip: The Salary Slip document
    """
    if not _needs_tax_summary_update(slip):
        logger.debug(f"Tax summary update not needed for {slip.name}")
        return
    
    try:
        logger.debug(f"Enqueueing tax summary update for {slip.name}")
        
        # Enqueue the update function
        enqueue(
            "payroll_indonesia.payroll_indonesia.utils.update_employee_tax_summary",
            employee=slip.employee,
            salary_slip=slip.name,
            queue="short",
            timeout=300
        )
        
        logger.info(f"Tax summary update enqueued for {slip.name}")
    
    except Exception as e:
        logger.exception(f"Error enqueueing tax summary update for {slip.name}: {e}")


def calculate_monthly_pro_rata(doc) -> float:
    """
    Calculate pro-rata factor for partial month work.

    Args:
        doc: The Salary Slip document

    Returns:
        float: Pro-rata factor (0.0-1.0)
    """
    try:
        if not doc.start_date or not doc.end_date:
            return 1.0
        
        # Get working days info
        total_working_days = cint(doc.total_working_days) or 22
        payment_days = flt(doc.payment_days) or total_working_days
        
        # Calculate pro-rata factor
        pro_rata = min(1.0, max(0.0, payment_days / total_working_days))
        
        logger.debug(f"Calculated pro-rata factor: {pro_rata} for Salary Slip {doc.name}")
        return pro_rata
    
    except Exception as e:
        logger.exception(f"Error calculating pro-rata for {doc.name}: {e}")
        return 1.0


def calculate_tax_amount(doc) -> float:
    """
    Calculate PPh 21 tax amount.

    Args:
        doc: The Salary Slip document

    Returns:
        float: Calculated tax amount
    """
    try:
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
        
        # Get tax method
        tax_method = "Progressive"
        if hasattr(doc, "is_using_ter") and doc.is_using_ter:
            tax_method = "TER"
        elif hasattr(doc, "is_december_override") and doc.is_december_override:
            tax_method = "December"
        
        # Calculate tax based on method
        tax_amount = 0.0
        
        # Import tax calculation functions dynamically to avoid circular imports
        if tax_method == "TER":
            try:
                from payroll_indonesia.override.salary_slip.ter_calculator import (
                    calculate_monthly_pph_with_ter
                )
                result = calculate_monthly_pph_with_ter(doc)
                tax_amount = result.get("monthly_tax", 0.0)
            except Exception as e:
                logger.exception(f"Error calculating TER tax for {doc.name}: {e}")
        
        elif tax_method == "December":
            try:
                from payroll_indonesia.override.salary_slip.tax_calculator import (
                    calculate_december_pph
                )
                result = calculate_december_pph(doc)
                tax_amount = result.get("correction", 0.0)
            except Exception as e:
                logger.exception(f"Error calculating December tax for {doc.name}: {e}")
        
        else:  # Progressive
            try:
                from payroll_indonesia.override.salary_slip.tax_calculator import (
                    calculate_monthly_pph_progressive
                )
                result = calculate_monthly_pph_progressive(doc)
                tax_amount = result.get("monthly_tax", 0.0)
            except Exception as e:
                logger.exception(f"Error calculating Progressive tax for {doc.name}: {e}")
        
        # Update component and document field
        pph21_component.amount = tax_amount
        doc.pph21 = tax_amount
        
        logger.debug(f"Calculated tax amount: {tax_amount} for Salary Slip {doc.name}")
        return tax_amount
    
    except Exception as e:
        logger.exception(f"Error calculating tax amount for {doc.name}: {e}")
        return 0.0


def calculate_employer_contributions(doc) -> Dict[str, float]:
    """
    Calculate employer BPJS contributions.

    Args:
        doc: The Salary Slip document

    Returns:
        Dict[str, float]: Employer contribution amounts by component
    """
    try:
        # Get configuration
        config = get_live_config()
        bpjs_config = config.get("bpjs", {})
        
        if not bpjs_config:
            logger.warning("BPJS configuration not found")
            return {}
        
        contributions = {}
        base_salary = doc.gross_pay or 0
        
        # Calculate BPJS Kesehatan Employer
        contributions["BPJS Kesehatan Employer"] = calc_bpjs(
            base_salary,
            bpjs_config.get("kesehatan_employer_percent", 4.0),
            max_salary=bpjs_config.get("kesehatan_max_salary", 12000000),
        )
        
        # Calculate BPJS JHT Employer
        contributions["BPJS JHT Employer"] = calc_bpjs(
            base_salary, bpjs_config.get("jht_employer_percent", 3.7)
        )
        
        # Calculate BPJS JP Employer
        contributions["BPJS JP Employer"] = calc_bpjs(
            base_salary,
            bpjs_config.get("jp_employer_percent", 2.0),
            max_salary=bpjs_config.get("jp_max_salary", 9077600),
        )
        
        # Calculate BPJS JKK
        contributions["BPJS JKK"] = calc_bpjs(base_salary, bpjs_config.get("jkk_percent", 0.24))
        
        # Calculate BPJS JKM
        contributions["BPJS JKM"] = calc_bpjs(base_salary, bpjs_config.get("jkm_percent", 0.3))
        
        # Calculate total
        contributions["total"] = sum(
            amount for key, amount in contributions.items() if key != "total"
        )
        
        logger.debug(f"Calculated employer contributions: {contributions}")
        return contributions
    
    except Exception as e:
        logger.exception(f"Error calculating employer contributions for {doc.name}: {e}")
        return {}


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
        logger.exception(f"Error retrieving components from structure {structure_name}: {e}")
    
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
        
        # Update YTD tax
        tax_amount = 0.0
        # Try to get from pph21 field first
        if hasattr(doc, "pph21"):
            tax_amount = flt(doc.pph21)
        else:
            # Otherwise, look for PPh 21 in deductions
            for deduction in doc.deductions:
                if deduction.salary_component == "PPh 21":
                    tax_amount = flt(deduction.amount)
                    break
        
        history.ytd_tax += tax_amount
        
        # Save history
        history.flags.ignore_permissions = True
        history.save()
        
        logger.debug(
            f"Updated salary history for employee {doc.employee}: "
            f"gross +{doc.gross_pay}, tax +{tax_amount}"
        )
    
    except Exception as e:
        logger.exception(f"Error updating employee history for {doc.employee}: {e}")


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
        logger.exception(f"Error storing employer contributions for {doc.name}: {e}")