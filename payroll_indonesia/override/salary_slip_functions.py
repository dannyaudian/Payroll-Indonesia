# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
Salary Slip Functions - Override for Indonesia-specific salary processing
"""

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate

from payroll_indonesia.constants import (
    BIAYA_JABATAN_PERCENT,
    BIAYA_JABATAN_MAX,
    MONTHS_PER_YEAR,
    TAX_DEDUCTION_EFFECT,
    TAX_OBJEK_EFFECT,
    NATURA_OBJEK_EFFECT,
)
from payroll_indonesia.override.salary_slip.tax_calculator import (
    calculate_december_pph,
    calculate_monthly_pph_progressive,
    categorize_components_by_tax_effect,
    get_ptkp_value,
    get_tax_status,
    get_slip_year_month,
    get_ytd_totals,
    is_december_calculation,
)
from payroll_indonesia.override.salary_slip.controller import (
    update_indonesia_tax_components,
    calculate_taxable_earnings,
    get_bpjs_deductions,
)
from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.payroll_indonesia import utils


def before_validate(doc, method=None):
    """
    Before validate hook for Salary Slip.

    Args:
        doc: Salary Slip document
        method: Method name (not used)
    """
    try:
        # Skip if document is already validated
        if hasattr(doc, "flags") and getattr(doc.flags, "skip_indonesia_hooks", False):
            return

        # Only process if Indonesia payroll is enabled
        if cint(getattr(doc, "calculate_indonesia_tax", 0)) != 1:
            return

        # Check if status_pajak is set, if not, try to get from employee
        if not getattr(doc, "status_pajak", None):
            doc.status_pajak = get_tax_status(doc)

        # Run validation
        validate_salary_slip(doc)

        logger.debug(f"Completed before_validate for slip {getattr(doc, 'name', 'unknown')}")

    except Exception as e:
        logger.exception(f"Error in before_validate: {str(e)}")


def validate(doc, method=None):
    """
    Validate hook for Salary Slip.

    Args:
        doc: Salary Slip document
        method: Method name (not used)
    """
    try:
        # Skip if document is already validated
        if hasattr(doc, "flags") and getattr(doc.flags, "skip_indonesia_hooks", False):
            return

        # Only process if Indonesia payroll is enabled
        if cint(getattr(doc, "calculate_indonesia_tax", 0)) != 1:
            return

        # Process Indonesia payroll calculations
        process_indonesia_payroll(doc)

        # Update custom fields for reporting
        _update_custom_fields(doc)

        logger.debug(f"Completed validate for slip {getattr(doc, 'name', 'unknown')}")

    except Exception as e:
        logger.exception(f"Error in validate: {str(e)}")


def before_save(doc, method=None):
    """
    Before save hook for Salary Slip.

    Args:
        doc: Salary Slip document
        method: Method name (not used)
    """
    try:
        # Skip if document is already processed
        if hasattr(doc, "flags") and getattr(doc.flags, "skip_indonesia_hooks", False):
            return

        # Only process if Indonesia payroll is enabled
        if cint(getattr(doc, "calculate_indonesia_tax", 0)) != 1:
            return

        # Update deduction amounts if needed
        _update_deduction_amounts(doc)

        logger.debug(f"Completed before_save for slip {getattr(doc, 'name', 'unknown')}")

    except Exception as e:
        logger.exception(f"Error in before_save: {str(e)}")


def after_save(doc, method=None):
    """
    After save hook for Salary Slip.

    Args:
        doc: Salary Slip document
        method: Method name (not used)
    """
    try:
        # Skip if document is already processed
        if hasattr(doc, "flags") and getattr(doc.flags, "skip_indonesia_hooks", False):
            return

        # Only process if Indonesia payroll is enabled
        if cint(getattr(doc, "calculate_indonesia_tax", 0)) != 1:
            return

        logger.debug(f"Completed after_save for slip {getattr(doc, 'name', 'unknown')}")

    except Exception as e:
        logger.exception(f"Error in after_save: {str(e)}")


def after_submit(doc, method=None):
    """
    After submit hook for Salary Slip.

    Args:
        doc: Salary Slip document
        method: Method name (not used)
    """
    try:
        # Skip if document is already processed
        if hasattr(doc, "flags") and getattr(doc.flags, "skip_indonesia_hooks", False):
            return

        # Only process if Indonesia payroll is enabled
        if cint(getattr(doc, "calculate_indonesia_tax", 0)) != 1:
            return

        # Update the Employee Tax Summary with this slip's data
        utils.update_employee_tax_summary(doc.employee, doc.name)

        logger.debug(f"Updated tax summary after submit for slip {getattr(doc, 'name', 'unknown')}")

    except Exception as e:
        logger.exception(f"Error in after_submit: {str(e)}")


def validate_salary_slip(doc):
    """
    Validate the salary slip for Indonesia-specific requirements.

    Args:
        doc: Salary Slip document
    """
    try:
        # Validate tax status is set
        tax_status = getattr(doc, "status_pajak", None)
        if not tax_status:
            # Try to get from employee
            employee = getattr(doc, "employee_doc", None)
            if not employee and hasattr(doc, "employee"):
                try:
                    employee = frappe.get_doc("Employee", doc.employee)
                    doc.employee_doc = employee
                except Exception:
                    pass

            if employee and hasattr(employee, "status_pajak") and employee.status_pajak:
                doc.status_pajak = employee.status_pajak
                logger.debug(f"Set tax status to {doc.status_pajak} from employee")
            else:
                frappe.msgprint(_("Tax status (PTKP) not set for employee. Using default TK0."))
                doc.status_pajak = "TK0"

        # Validate tax method
        tax_method = getattr(doc, "tax_method", None)
        if not tax_method:
            doc.tax_method = "Progressive"
        elif tax_method not in ["Progressive", "TER"]:
            frappe.throw(_("Invalid tax method. Must be 'Progressive' or 'TER'."))

        # Validate TER category if using TER method
        if tax_method == "TER":
            ter_category = getattr(doc, "ter_category", None)
            if not ter_category:
                # Will be set by tax calculation
                pass
            elif ter_category not in ["TER A", "TER B", "TER C"]:
                frappe.throw(_("Invalid TER category. Must be 'TER A', 'TER B', or 'TER C'."))

        logger.debug(f"Validated salary slip {getattr(doc, 'name', 'unknown')}")

    except Exception as e:
        logger.exception(f"Error validating salary slip: {str(e)}")


def process_indonesia_payroll(doc):
    """
    Process Indonesia-specific payroll calculations.

    Args:
        doc: Salary Slip document
    """
    try:
        # Calculate tax components
        update_indonesia_tax_components(doc)

        # Set taxable earnings for reporting
        doc.taxable_earnings = calculate_taxable_earnings(doc)

        # Check if Employee Tax Summary exists for this employee/year
        ensure_employee_tax_summary_integration(doc)

        logger.debug(f"Processed Indonesia payroll for slip {getattr(doc, 'name', 'unknown')}")

    except Exception as e:
        logger.exception(f"Error processing Indonesia payroll: {str(e)}")


def ensure_employee_tax_summary_integration(doc):
    """
    Ensure proper integration with Employee Tax Summary.

    This function checks if an Employee Tax Summary exists for the current
    employee and year, and updates the slip with YTD data if available.

    Args:
        doc: Salary Slip document
    """
    try:
        employee = getattr(doc, "employee", None)
        if not employee:
            return

        # Get year
        year, month = get_slip_year_month(doc)

        # Check if Employee Tax Summary exists
        tax_summary = frappe.get_all(
            "Employee Tax Summary",
            filters={"employee": employee, "year": year},
            fields=[
                "ytd_gross_pay",
                "ytd_tax",
                "ytd_bpjs",
                "ytd_taxable_components",
                "ytd_tax_deductions",
                "tax_method",
                "is_using_ter",
                "ter_rate",
            ],
            limit=1,
        )

        if not tax_summary:
            logger.debug(f"No Employee Tax Summary found for {employee}, year {year}")
            return

        # Update slip with YTD data from tax summary
        if hasattr(doc, "ytd_gross_pay"):
            doc.ytd_gross_pay = flt(tax_summary[0].ytd_gross_pay)
        if hasattr(doc, "ytd_tax"):
            doc.ytd_tax = flt(tax_summary[0].ytd_tax)
        if hasattr(doc, "ytd_bpjs"):
            doc.ytd_bpjs = flt(tax_summary[0].ytd_bpjs)
        if hasattr(doc, "ytd_taxable_components"):
            doc.ytd_taxable_components = flt(tax_summary[0].ytd_taxable_components)
        if hasattr(doc, "ytd_tax_deductions"):
            doc.ytd_tax_deductions = flt(tax_summary[0].ytd_tax_deductions)

        # Update tax method if slip doesn't have it set
        if not getattr(doc, "tax_method", None):
            doc.tax_method = tax_summary[0].tax_method

        # Update TER info if using TER
        if cint(tax_summary[0].is_using_ter) == 1:
            if hasattr(doc, "is_using_ter"):
                doc.is_using_ter = 1
            if hasattr(doc, "ter_rate") and not doc.ter_rate:
                doc.ter_rate = flt(tax_summary[0].ter_rate)

        logger.debug(f"Updated slip with YTD data from Employee Tax Summary")

    except Exception as e:
        logger.exception(f"Error ensuring Employee Tax Summary integration: {str(e)}")


def _update_deduction_amounts(doc):
    """
    Update deduction amounts based on tax effect types.

    Args:
        doc: Salary Slip document
    """
    try:
        # Get categorized components
        tax_components = categorize_components_by_tax_effect(doc)

        # Get BPJS details
        bpjs = get_bpjs_deductions(doc)

        # Update BPJS fields
        if hasattr(doc, "total_bpjs"):
            doc.total_bpjs = bpjs["total_employee"]

        if hasattr(doc, "jht_employee"):
            doc.jht_employee = bpjs["jht_employee"]

        if hasattr(doc, "jp_employee"):
            doc.jp_employee = bpjs["jp_employee"]

        if hasattr(doc, "kesehatan_employee"):
            doc.kesehatan_employee = bpjs["jkn_employee"]

        # Update tax deduction fields
        if hasattr(doc, "ytd_tax_deductions"):
            doc.ytd_tax_deductions = tax_components["totals"].get(TAX_DEDUCTION_EFFECT, 0)

        # Update PPh 21
        pph21_amount = 0
        if hasattr(doc, "deductions") and doc.deductions:
            for deduction in doc.deductions:
                if deduction.salary_component == "PPh 21":
                    pph21_amount = flt(deduction.amount)
                    break

        if hasattr(doc, "pph21"):
            doc.pph21 = pph21_amount

        logger.debug(f"Updated deduction amounts for slip {getattr(doc, 'name', 'unknown')}")

    except Exception as e:
        logger.exception(f"Error updating deduction amounts: {str(e)}")


def _update_custom_fields(doc):
    """
    Update custom fields for reporting.

    Args:
        doc: Salary Slip document
    """
    try:
        # Update taxable earnings
        if hasattr(doc, "taxable_earnings"):
            doc.taxable_earnings = calculate_taxable_earnings(doc)

        # Update gross pay in base currency
        if hasattr(doc, "base_gross_pay") and hasattr(doc, "gross_pay"):
            doc.base_gross_pay = doc.gross_pay

        # Update net pay in base currency
        if hasattr(doc, "base_net_pay") and hasattr(doc, "net_pay"):
            doc.base_net_pay = doc.net_pay

        # Update total deduction in base currency
        if hasattr(doc, "base_total_deduction") and hasattr(doc, "total_deduction"):
            doc.base_total_deduction = doc.total_deduction

        # Update year and month fields
        year, month = get_slip_year_month(doc)

        if hasattr(doc, "salary_year"):
            doc.salary_year = year

        if hasattr(doc, "salary_month"):
            doc.salary_month = month

        # Update YTD fields from tax calculation
        if hasattr(doc, "ytd_gross") and not doc.ytd_gross:
            ytd = get_ytd_totals(doc)
            if hasattr(doc, "ytd_gross"):
                doc.ytd_gross = ytd.get("gross", 0)
            if hasattr(doc, "ytd_bpjs"):
                doc.ytd_bpjs = ytd.get("bpjs", 0)
            if hasattr(doc, "ytd_pph21"):
                doc.ytd_pph21 = ytd.get("pph21", 0)

        # Update December flag
        if hasattr(doc, "is_december_slip"):
            doc.is_december_slip = 1 if is_december_calculation(doc) else 0

        # Update koreksi_pph21 for December
        if is_december_calculation(doc):
            # Use correction amount from December tax calculation
            _, details = calculate_december_pph(doc)
            doc.koreksi_pph21 = flt(details.get("correction_amount", 0))

        # Update is_final_gabung_suami
        if hasattr(doc, "is_final_gabung_suami"):
            employee_doc = frappe.get_doc("Employee", doc.employee)
            doc.is_final_gabung_suami = cint(getattr(employee_doc, "npwp_gabung_suami", 0))

        # Update netto and related tax fields
        if (
            hasattr(doc, "netto")
            or hasattr(doc, "biaya_jabatan")
            or hasattr(doc, "annual_taxable_income")
            or hasattr(doc, "annual_pkp")
        ):
            tax_components = categorize_components_by_tax_effect(doc)

            gross_income = tax_components["totals"].get(TAX_OBJEK_EFFECT, 0)
            gross_income += tax_components["totals"].get(NATURA_OBJEK_EFFECT, 0)
            deductions = tax_components["totals"].get(TAX_DEDUCTION_EFFECT, 0)

            netto = gross_income - deductions

            if hasattr(doc, "netto"):
                doc.netto = netto

            if hasattr(doc, "biaya_jabatan"):
                doc.biaya_jabatan = min(
                    gross_income * BIAYA_JABATAN_PERCENT / 100,
                    BIAYA_JABATAN_MAX,
                )

            annual_taxable = gross_income * MONTHS_PER_YEAR

            if hasattr(doc, "annual_taxable_income"):
                doc.annual_taxable_income = annual_taxable

            if hasattr(doc, "annual_pkp"):
                annual_ptkp = get_ptkp_value(get_tax_status(doc))
                annual_deductions = deductions * MONTHS_PER_YEAR
                annual_biaya_jabatan = min(
                    annual_taxable * BIAYA_JABATAN_PERCENT / 100,
                    BIAYA_JABATAN_MAX * MONTHS_PER_YEAR,
                )
                annual_pkp = max(
                    0,
                    annual_taxable - annual_biaya_jabatan - annual_deductions - annual_ptkp,
                )
                annual_pkp = annual_pkp - (annual_pkp % 1000)
                doc.annual_pkp = annual_pkp

        logger.debug(f"Updated custom fields for slip {getattr(doc, 'name', 'unknown')}")

    except Exception as e:
        logger.exception(f"Error updating custom fields: {str(e)}")


def get_component_details(slip, component_name):
    """
    Get details for a specific component in a salary slip.

    Args:
        slip: Salary Slip document
        component_name: Name of the salary component

    Returns:
        Dict: Dictionary with component details
    """
    try:
        result = {"found": False, "type": None, "amount": 0.0, "tax_effect": None}

        # Check earnings
        if hasattr(slip, "earnings") and slip.earnings:
            for earning in slip.earnings:
                if earning.salary_component == component_name:
                    result["found"] = True
                    result["type"] = "Earning"
                    result["amount"] = flt(earning.amount)
                    result["tax_effect"] = frappe.db.get_value(
                        "Salary Component", component_name, "tax_effect_type"
                    )
                    return result

        # Check deductions
        if hasattr(slip, "deductions") and slip.deductions:
            for deduction in slip.deductions:
                if deduction.salary_component == component_name:
                    result["found"] = True
                    result["type"] = "Deduction"
                    result["amount"] = flt(deduction.amount)
                    result["tax_effect"] = frappe.db.get_value(
                        "Salary Component", component_name, "tax_effect_type"
                    )
                    return result

        return result

    except Exception as e:
        logger.exception(f"Error getting component details for {component_name}: {str(e)}")
        return {"found": False, "type": None, "amount": 0.0, "tax_effect": None}
