# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:45:27 by dannyaudian

"""
Helper functions for Salary Slip processing - without calculator duplication.
"""

from typing import Any, Dict

import frappe
from frappe import _
from frappe.utils import getdate, flt

# Calculator module imports
import payroll_indonesia.override.salary_slip.bpjs_calculator as bpjs_calc
import payroll_indonesia.override.salary_slip.tax_calculator as tax_calc
import payroll_indonesia.override.salary_slip.ter_calculator as ter_calc
import payroll_indonesia.override.salary_slip.salary_utils as utils

# Config
from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.frappe_helpers import logger


def update_component_amount(slip: Any) -> Dict[str, Any]:
    """
    Update BPJS and PPh 21 component amounts in salary slip.

    Args:
        slip: Salary slip document

    Returns:
        Dict[str, Any]: Updated component details
    """
    try:
        result = {}

        # Calculate BPJS components
        bpjs_components = bpjs_calc.calculate_components(slip)
        result["bpjs"] = bpjs_components

        # Update BPJS component amounts in deductions
        _update_bpjs_components(slip, bpjs_components)

        # Get configuration
        cfg = get_live_config()

        # Determine tax calculation method
        is_december = _is_december_calculation(slip)
        is_using_ter = _should_use_ter(slip, cfg)

        # Calculate tax based on method
        if is_december:
            tax_result = tax_calc.calculate_december_pph(slip)
            result["tax_method"] = "december"
        elif is_using_ter:
            tax_result = ter_calc.calculate_monthly_pph_with_ter(slip)
            result["tax_method"] = "ter"
        else:
            tax_result = tax_calc.calculate_monthly_pph_progressive(slip)
            result["tax_method"] = "progressive"

        result["tax"] = tax_result

        # Update PPh 21 component amount
        _update_pph21_component(slip)

        # Update total deduction
        _update_totals(slip)

        # Calculate YTD and YTM values
        ytd_values = utils.calculate_ytd_and_ytm(slip)
        result["ytd"] = ytd_values

        # Set YTD values on slip
        _set_ytd_values(slip, ytd_values)

        logger.info(f"Updated components for slip {getattr(slip, 'name', 'unknown')}")
        return result

    except Exception as e:
        logger.exception(f"Error updating component amounts: {e}")
        frappe.throw(_("Error updating component amounts: {0}").format(str(e)))


def _update_bpjs_components(slip: Any, components: Dict[str, float]) -> None:
    """
    Update BPJS component amounts in salary slip deductions.

    Args:
        slip: Salary slip document
        components: Dictionary of calculated BPJS components
    """
    if not hasattr(slip, "deductions") or not slip.deductions:
        return

    # Mapping of component names to values
    component_map = {
        "BPJS Kesehatan Employee": components.get("kesehatan_employee", 0),
        "BPJS JHT Employee": components.get("jht_employee", 0),
        "BPJS JP Employee": components.get("jp_employee", 0),
    }

    # Update components
    for deduction in slip.deductions:
        component_name = getattr(deduction, "salary_component", "")
        if component_name in component_map:
            deduction.amount = component_map[component_name]


def _update_pph21_component(slip: Any) -> None:
    """
    Update PPh 21 component amount in salary slip deductions.

    Args:
        slip: Salary slip document
    """
    if not hasattr(slip, "deductions") or not slip.deductions:
        return

    pph21_amount = flt(getattr(slip, "pph21", 0))
    pph21_found = False

    # Look for existing PPh 21 component
    for deduction in slip.deductions:
        component_name = getattr(deduction, "salary_component", "")
        if component_name == "PPh 21":
            deduction.amount = pph21_amount
            pph21_found = True
            break

    # Add PPh 21 component if not found and amount > 0
    if not pph21_found and pph21_amount > 0:
        slip.append(
            "deductions",
            {"salary_component": "PPh 21", "amount": pph21_amount, "default_amount": pph21_amount},
        )


def _update_totals(slip: Any) -> None:
    """
    Update total deduction and net pay in salary slip.

    Args:
        slip: Salary slip document
    """
    if hasattr(slip, "deductions") and slip.deductions:
        # Calculate total deductions
        total_deduction = sum(flt(d.amount) for d in slip.deductions)

        # Update total_deduction field
        if hasattr(slip, "total_deduction"):
            slip.total_deduction = total_deduction

        # Update net_pay field
        if hasattr(slip, "gross_pay") and hasattr(slip, "net_pay"):
            slip.net_pay = flt(slip.gross_pay) - total_deduction


def _set_ytd_values(slip: Any, ytd_values: Dict[str, float]) -> None:
    """
    Set YTD values on salary slip.

    Args:
        slip: Salary slip document
        ytd_values: Dictionary of YTD values
    """
    # Set YTD values if fields exist
    if hasattr(slip, "ytd_gross_pay"):
        slip.ytd_gross_pay = ytd_values.get("ytd", {}).get("ytd_gross", 0)

    if hasattr(slip, "ytd_bpjs_deductions"):
        slip.ytd_bpjs_deductions = ytd_values.get("ytd", {}).get("ytd_bpjs", 0)

    if hasattr(slip, "ytd_pph21"):
        slip.ytd_pph21 = ytd_values.get("ytd", {}).get("ytd_pph21", 0)

    # Try to persist values if document has been saved
    if getattr(slip, "name", "").startswith("new-") is False:
        try:
            for field, key in [
                ("ytd_gross_pay", "ytd_gross"),
                ("ytd_bpjs_deductions", "ytd_bpjs"),
                ("ytd_pph21", "ytd_pph21"),
            ]:
                if hasattr(slip, field):
                    slip.db_set(
                        field, 
                        ytd_values.get("ytd", {}).get(key, 0), 
                        update_modified=False
                    )
        except Exception as e:
            logger.warning(f"Could not persist YTD values: {e}")


def _is_december_calculation(slip: Any) -> bool:
    """
    Determine if slip should use December calculation logic.

    Args:
        slip: Salary slip document

    Returns:
        bool: True if December or override flag is set
    """
    # Check explicit override flag
    if getattr(slip, "is_december_override", 0):
        return True

    # Check if month is December
    if hasattr(slip, "end_date") and slip.end_date:
        end_date = getdate(slip.end_date)
        return end_date.month == 12

    return False


def _should_use_ter(slip: Any, cfg: Dict[str, Any]) -> bool:
    """
    Determine if TER calculation should be used.

    Args:
        slip: Salary slip document
        cfg: Configuration dictionary

    Returns:
        bool: True if TER should be used
    """
    # Check explicit flag first
    if getattr(slip, "is_using_ter", 0):
        return True

    # Check config setting
    use_ter = cfg.get("tax", {}).get("use_ter_by_default", 0)

    # Check employee category if needed
    if use_ter and hasattr(slip, "employee_doc"):
        emp_category = getattr(slip.employee_doc, "employee_category", "")
        excluded_categories = cfg.get("tax", {}).get("ter_excluded_categories", [])

        if emp_category in excluded_categories:
            return False

    return bool(use_ter)


def _needs_tax_summary_update(slip: Any) -> bool:
    """
    Check if tax summary needs to be updated.

    Args:
        slip: Salary slip document

    Returns:
        bool: True if tax summary update is needed
    """
    # Check if slip has PPh 21 component
    has_pph21 = False
    pph21_amount = flt(getattr(slip, "pph21", 0))

    if pph21_amount > 0:
        has_pph21 = True
    else:
        # Check deductions
        if hasattr(slip, "deductions") and slip.deductions:
            for d in slip.deductions:
                if getattr(d, "salary_component", "") == "PPh 21" and flt(d.amount) > 0:
                    has_pph21 = True
                    break

    # Check if slip has BPJS component
    has_bpjs = False
    bpjs_total = flt(getattr(slip, "total_bpjs", 0))

    if bpjs_total > 0:
        has_bpjs = True
    else:
        # Check deductions
        if hasattr(slip, "deductions") and slip.deductions:
            for d in slip.deductions:
                if any(
                    bpjs_type in getattr(d, "salary_component", "")
                    for bpjs_type in ["BPJS Kesehatan", "BPJS JHT", "BPJS JP"]
                ):
                    has_bpjs = True
                    break

    return has_pph21 or has_bpjs


def enqueue_tax_summary_update(slip: Any) -> None:
    """
    Enqueue a background job to update the tax summary.

    Args:
        slip: Salary slip document
    """
    # Check document status - only process submitted slips
    if getattr(slip, "docstatus", 0) != 1:  # 1 = Submitted
        logger.debug(f"Skip tax summary update for non-submitted slip {slip.name}")
        return

    # Enqueue the job
    frappe.enqueue(
        "payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary."
        "employee_tax_summary.create_from_salary_slip",
        queue="long",
        timeout=600,
        salary_slip=slip.name,
        is_async=True,
        job_name=f"tax_summary_update_{slip.name}",
        now=False,  # Run in background
    )

    logger.info(f"Queued tax summary update for slip {slip.name}")

    # Add note to payroll_note field if it exists
    if hasattr(slip, "payroll_note"):
        note = f"Tax summary update queued (job: tax_summary_update_{slip.name})"

        try:
            current_note = getattr(slip, "payroll_note", "")
            new_note = f"{current_note}\n{note}" if current_note else note
            slip.db_set("payroll_note", new_note, update_modified=False)
        except Exception as e:
            logger.warning(f"Could not update payroll note: {e}")


def initialize_fields(slip: Any) -> None:
    """
    Initialize additional fields required for Indonesian payroll.

    Args:
        slip: Salary slip document
    """
    default_fields = {
        "biaya_jabatan": 0,
        "netto": 0,
        "total_bpjs": 0,
        "kesehatan_employee": 0,
        "jht_employee": 0,
        "jp_employee": 0,
        "is_using_ter": 0,
        "ter_rate": 0,
        "ter_category": "",
        "koreksi_pph21": 0,
        "payroll_note": "",
        "npwp": "",
        "ktp": "",
        "ytd_gross_pay": 0,
        "ytd_bpjs_deductions": 0,
        "ytd_pph21": 0,
        "pph21": 0,
    }

    # Set default values for fields
    for field, default in default_fields.items():
        if not hasattr(slip, field) or getattr(slip, field) is None:
            setattr(slip, field, default)

            # Try to persist with db_set if possible
            if getattr(slip, "name", "").startswith("new-") is False:
                try:
                    slip.db_set(field, default, update_modified=False)
                except Exception:
                    pass  # Ignore errors for unsaved documents


def salary_slip_post_submit(slip: Any) -> None:
    """
    Process tasks after salary slip submission.
    
    This function handles:
    - Updating tax summary via background queue
    - Updating YTD values
    - Any other post-submission tasks
    
    Args:
        slip: Salary slip document
    """
    try:
        # Calculate components one more time to ensure latest values
        update_component_amount(slip)
        
        # Check if tax summary update is needed and enqueue it
        if _needs_tax_summary_update(slip):
            enqueue_tax_summary_update(slip)
        
        # Log completion
        logger.info(f"Post-submit processing completed for salary slip {slip.name}")
        
    except Exception as e:
        logger.exception(f"Error in post-submit processing for {slip.name}: {e}")
        # Non-critical function, don't raise to calling function
        frappe.log_error(
            f"Error in post-submit processing for {slip.name}: {e}",
            "Salary Slip Post Submit Error"
        )
