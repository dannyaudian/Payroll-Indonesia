# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
Salary Slip Controller module - Indonesia-specific logic for salary processing
"""

import logging
from typing import Dict, List, Tuple, Any, Optional, Union

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, date_diff, add_months

from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.config.config import get_component_tax_effect
from payroll_indonesia.constants import (
    TAX_DEDUCTION_EFFECT,
    TAX_OBJEK_EFFECT,
    TAX_NON_OBJEK_EFFECT,
    NATURA_OBJEK_EFFECT,
    NATURA_NON_OBJEK_EFFECT,
)
from payroll_indonesia.override.salary_slip.tax_calculator import (
    calculate_monthly_pph_progressive,
    calculate_december_pph,
    calculate_monthly_pph_with_ter,
    is_december_calculation,
    get_slip_year_month,
    update_slip_fields,
)

__all__ = [
    "IndonesiaPayrollSalarySlip",  # Add to public API
    "update_indonesia_tax_components",
    "calculate_taxable_earnings",
    "get_bpjs_deductions",
    "update_slip_with_tax_details",
    "process_indonesia_taxes",
    "ensure_employee_tax_summary_integration",
]


class IndonesiaPayrollSalarySlip:
    """
    Class to handle Indonesia-specific salary slip processing.
    This is the main integration point for salary slip customizations.
    """

    def __init__(self, doc=None):
        """Initialize with optional salary slip document"""
        self.doc = doc

    def calculate_tax(self) -> float:
        """
        Calculate PPh 21 tax amount.

        Returns:
            float: Calculated tax amount
        """
        if not self.doc:
            return 0.0

        # Update tax components in the document
        update_indonesia_tax_components(self.doc)

        # Get the PPh 21 component amount
        pph21_amount = 0
        if hasattr(self.doc, "deductions") and self.doc.deductions:
            for deduction in self.doc.deductions:
                if deduction.salary_component == "PPh 21":
                    pph21_amount = flt(deduction.amount)
                    break

        return pph21_amount

    def update_custom_fields(self) -> None:
        """Update Indonesia-specific custom fields in the document"""
        if not self.doc:
            return

        # Skip if Indonesia payroll not enabled
        if not cint(getattr(self.doc, "calculate_indonesia_tax", 0)):
            return

        # Update YTD data
        self.update_ytd_data()

        # Update tax fields
        self.update_tax_fields()

        # Update BPJS fields
        self.update_bpjs_fields()

    def update_ytd_data(self) -> None:
        """Update Year-to-Date data from Employee Tax Summary"""
        if not self.doc:
            return

        # Skip if Indonesia payroll not enabled
        if not cint(getattr(self.doc, "calculate_indonesia_tax", 0)):
            return

        try:
            employee = getattr(self.doc, "employee", None)
            if not employee:
                return

            # Get year from slip
            year, _ = get_slip_year_month(self.doc)

            # Try to get YTD data from Employee Tax Summary
            tax_summary = frappe.get_all(
                "Employee Tax Summary",
                filters={"employee": employee, "year": year},
                fields=[
                    "ytd_gross_pay",
                    "ytd_tax",
                    "ytd_bpjs",
                    "ytd_taxable_components",
                    "ytd_tax_deductions",
                ],
                limit=1,
            )

            if tax_summary:
                # Update YTD fields
                if hasattr(self.doc, "ytd_gross_pay"):
                    self.doc.ytd_gross_pay = flt(tax_summary[0].ytd_gross_pay)
                if hasattr(self.doc, "ytd_tax"):
                    self.doc.ytd_tax = flt(tax_summary[0].ytd_tax)
                if hasattr(self.doc, "ytd_bpjs"):
                    self.doc.ytd_bpjs = flt(tax_summary[0].ytd_bpjs)
                if hasattr(self.doc, "ytd_taxable_components"):
                    self.doc.ytd_taxable_components = flt(tax_summary[0].ytd_taxable_components)
                if hasattr(self.doc, "ytd_tax_deductions"):
                    self.doc.ytd_tax_deductions = flt(tax_summary[0].ytd_tax_deductions)

                logger.debug(f"Updated YTD data from Employee Tax Summary for {employee}")
            else:
                logger.debug(f"No Employee Tax Summary found for {employee}, year {year}")

        except Exception as e:
            logger.exception(f"Error updating YTD data: {str(e)}")

    def update_tax_fields(self) -> None:
        """Update tax-related fields in the document"""
        if not self.doc:
            return

        # Skip if Indonesia payroll not enabled
        if not cint(getattr(self.doc, "calculate_indonesia_tax", 0)):
            return

        try:
            # Get tax method
            tax_method = getattr(self.doc, "tax_method", "Progressive")

            # Update TER fields if using TER
            if tax_method == "TER":
                if hasattr(self.doc, "is_using_ter"):
                    self.doc.is_using_ter = 1

            # Update December fields if December calculation
            if is_december_calculation(self.doc):
                if hasattr(self.doc, "is_december_override"):
                    self.doc.is_december_override = 1

            # Update tax status from employee if not set
            if not getattr(self.doc, "tax_status", None):
                employee = getattr(self.doc, "employee_doc", None)
                if not employee and hasattr(self.doc, "employee"):
                    try:
                        employee = frappe.get_doc("Employee", self.doc.employee)
                        self.doc.employee_doc = employee
                    except Exception:
                        pass

                if employee and hasattr(employee, "status_pajak") and employee.status_pajak:
                    self.doc.tax_status = employee.status_pajak

            # Update NPWP gabung suami
            if hasattr(self.doc, "is_final_gabung_suami"):
                employee = getattr(self.doc, "employee_doc", None)
                if not employee and hasattr(self.doc, "employee"):
                    try:
                        employee = frappe.get_doc("Employee", self.doc.employee)
                        self.doc.employee_doc = employee
                    except Exception:
                        pass

                if employee and hasattr(employee, "npwp_gabung_suami"):
                    self.doc.is_final_gabung_suami = cint(employee.npwp_gabung_suami)

        except Exception as e:
            logger.exception(f"Error updating tax fields: {str(e)}")

    def update_bpjs_fields(self) -> None:
        """Update BPJS-related fields in the document"""
        if not self.doc:
            return

        # Skip if Indonesia payroll not enabled
        if not cint(getattr(self.doc, "calculate_indonesia_tax", 0)):
            return

        try:
            # Get BPJS deductions
            bpjs = get_bpjs_deductions(self.doc)

            # Update fields
            if hasattr(self.doc, "total_bpjs"):
                self.doc.total_bpjs = bpjs["total_employee"]

            if hasattr(self.doc, "kesehatan_employee"):
                self.doc.kesehatan_employee = bpjs["jkn_employee"]

            if hasattr(self.doc, "jht_employee"):
                self.doc.jht_employee = bpjs["jht_employee"]

            if hasattr(self.doc, "jp_employee"):
                self.doc.jp_employee = bpjs["jp_employee"]

            # Employer BPJS
            if hasattr(self.doc, "kesehatan_employer"):
                self.doc.kesehatan_employer = bpjs.get("jkn_employer", 0)

            if hasattr(self.doc, "jht_employer"):
                self.doc.jht_employer = bpjs.get("jht_employer", 0)

            if hasattr(self.doc, "jp_employer"):
                self.doc.jp_employer = bpjs.get("jp_employer", 0)

            if hasattr(self.doc, "jkk_employer"):
                self.doc.jkk_employer = bpjs.get("jkk_employer", 0)

            if hasattr(self.doc, "jkm_employer"):
                self.doc.jkm_employer = bpjs.get("jkm_employer", 0)

            if hasattr(self.doc, "total_bpjs_employer"):
                self.doc.total_bpjs_employer = bpjs.get("total_employer", 0)

        except Exception as e:
            logger.exception(f"Error updating BPJS fields: {str(e)}")


def calculate_taxable_earnings(doc: Any) -> float:
    """
    Calculate taxable earnings based on component tax effect type.

    Args:
        doc: Salary Slip document

    Returns:
        float: Total taxable earnings
    """
    try:
        taxable_earnings = 0.0

        # Process earnings
        if hasattr(doc, "earnings") and doc.earnings:
            for earning in doc.earnings:
                component = earning.salary_component
                amount = flt(earning.amount)

                # Skip zero amounts
                if amount <= 0:
                    continue

                # Get tax effect for this component
                tax_effect = get_component_tax_effect(component, "Earning")

                # Add to taxable earnings if it's an objek pajak or taxable natura
                if tax_effect == TAX_OBJEK_EFFECT or tax_effect == NATURA_OBJEK_EFFECT:
                    taxable_earnings += amount
                    logger.debug(f"Added taxable earning: {component} = {amount}")

        logger.debug(f"Total taxable earnings: {taxable_earnings}")
        return taxable_earnings

    except Exception as e:
        logger.exception(f"Error calculating taxable earnings: {str(e)}")
        return 0.0


def get_bpjs_deductions(doc: Any) -> Dict[str, float]:
    """
    Get BPJS deductions based on tax effect type.

    Args:
        doc: Salary Slip document

    Returns:
        Dict[str, float]: Dictionary with BPJS deduction details
    """
    try:
        result = {
            "jht_employee": 0.0,
            "jp_employee": 0.0,
            "jkn_employee": 0.0,
            "total_employee": 0.0,
            "jht_employer": 0.0,
            "jp_employer": 0.0,
            "jkn_employer": 0.0,
            "jkk_employer": 0.0,
            "jkm_employer": 0.0,
            "total_employer": 0.0,
            "total_combined": 0.0,
        }

        # Process deductions
        if hasattr(doc, "deductions") and doc.deductions:
            for deduction in doc.deductions:
                component = deduction.salary_component
                amount = flt(deduction.amount)

                # Skip zero amounts
                if amount <= 0:
                    continue

                # Get tax effect for this component
                tax_effect = get_component_tax_effect(component, "Deduction")

                # Check if this is a tax deduction (BPJS is typically a tax deduction)
                if tax_effect == TAX_DEDUCTION_EFFECT:
                    # Categorize based on component name
                    # This still relies on component naming but with tax effect as first filter
                    component_lower = component.lower()

                    if "jht" in component_lower and "employee" in component_lower:
                        result["jht_employee"] += amount
                        result["total_employee"] += amount
                    elif "jp" in component_lower and "employee" in component_lower:
                        result["jp_employee"] += amount
                        result["total_employee"] += amount
                    elif "jkn" in component_lower and "employee" in component_lower:
                        result["jkn_employee"] += amount
                        result["total_employee"] += amount
                    elif "jht" in component_lower and "employer" in component_lower:
                        result["jht_employer"] += amount
                        result["total_employer"] += amount
                    elif "jp" in component_lower and "employer" in component_lower:
                        result["jp_employer"] += amount
                        result["total_employer"] += amount
                    elif "jkn" in component_lower and "employer" in component_lower:
                        result["jkn_employer"] += amount
                        result["total_employer"] += amount
                    elif "jkk" in component_lower:
                        result["jkk_employer"] += amount
                        result["total_employer"] += amount
                    elif "jkm" in component_lower:
                        result["jkm_employer"] += amount
                        result["total_employer"] += amount
                    elif "bpjs" in component_lower:
                        # Generic BPJS component - add to employee portion
                        result["total_employee"] += amount

        # Calculate total
        result["total_combined"] = result["total_employee"] + result["total_employer"]

        return result

    except Exception as e:
        logger.exception(f"Error getting BPJS deductions: {str(e)}")
        return {
            "jht_employee": 0.0,
            "jp_employee": 0.0,
            "jkn_employee": 0.0,
            "total_employee": 0.0,
            "jht_employer": 0.0,
            "jp_employer": 0.0,
            "jkn_employer": 0.0,
            "jkk_employer": 0.0,
            "jkm_employer": 0.0,
            "total_employer": 0.0,
            "total_combined": 0.0,
        }


def update_slip_with_tax_details(doc: Any, details: Dict[str, Any]) -> None:
    """
    Update salary slip with tax calculation details.

    Args:
        doc: Salary Slip document
        details: Tax calculation details
    """
    try:
        # Update standard fields
        updates = {
            "tax_status": details.get("tax_status", ""),
            "ptkp_value": flt(details.get("ptkp_value", 0)),
            "monthly_taxable": flt(details.get("monthly_taxable", 0)),
            "annual_taxable": flt(details.get("annual_taxable", 0)),
        }

        # Add TER specific fields
        if "ter_category" in details:
            updates["ter_category"] = details.get("ter_category", "")
            updates["ter_rate"] = flt(details.get("ter_rate", 0))

        if "monthly_gross_for_ter" in details:
            updates["monthly_gross_for_ter"] = flt(details.get("monthly_gross_for_ter", 0))

        # Add progressive tax specific fields
        if "biaya_jabatan" in details:
            updates["biaya_jabatan"] = flt(details.get("biaya_jabatan", 0))
            updates["tax_deductions"] = flt(details.get("tax_deductions", 0))
            updates["annual_pkp"] = flt(details.get("annual_pkp", 0))
            updates["annual_tax"] = flt(details.get("annual_tax", 0))

        # Add December specific fields
        if "ytd_gross" in details:
            updates["ytd_gross"] = flt(details.get("ytd_gross", 0))
            updates["ytd_bpjs"] = flt(details.get("ytd_bpjs", 0))
            updates["ytd_pph21"] = flt(details.get("ytd_pph21", 0))
            updates["december_tax"] = flt(details.get("december_tax", 0))

            # Add correction_amount if available
            if "correction_amount" in details:
                updates["koreksi_pph21"] = flt(details.get("correction_amount", 0))

        # Store tax bracket details as JSON
        if "tax_brackets" in details and details["tax_brackets"]:
            updates["tax_brackets_json"] = frappe.as_json(details["tax_brackets"])

        # Store component details as JSON
        if "components" in details and details["components"]:
            updates["tax_components_json"] = frappe.as_json(details["components"])

        # Update the document
        update_slip_fields(doc, updates)

    except Exception as e:
        logger.exception(f"Error updating slip with tax details: {str(e)}")


def process_indonesia_taxes(doc: Any) -> float:
    """
    Process Indonesia-specific tax calculations.

    Args:
        doc: Salary Slip document

    Returns:
        float: Calculated PPh 21 amount
    """
    try:
        # Skip if not enabled
        if not cint(getattr(doc, "calculate_indonesia_tax", 0)):
            logger.debug(
                f"Indonesia tax calculation not enabled for slip {getattr(doc, 'name', 'unknown')}"
            )
            return 0.0

        # Get tax method
        tax_method = getattr(doc, "tax_method", "Progressive")
        logger.debug(f"Using tax method: {tax_method}")

        # Calculate based on method
        if tax_method == "TER":
            tax_amount, details = calculate_monthly_pph_with_ter(doc)
        elif is_december_calculation(doc):
            tax_amount, details = calculate_december_pph(doc)
        else:
            tax_amount, details = calculate_monthly_pph_progressive(doc)

        # Update slip with calculation details
        update_slip_with_tax_details(doc, details)

        logger.debug(f"Tax calculation result: {tax_amount}")
        return flt(tax_amount, 2)

    except Exception as e:
        logger.exception(f"Error processing Indonesia taxes: {str(e)}")
        return 0.0


def update_indonesia_tax_components(doc: Any) -> None:
    """
    Update tax components in the salary slip based on calculation.

    Args:
        doc: Salary Slip document
    """
    try:
        # Skip if not enabled
        if not cint(getattr(doc, "calculate_indonesia_tax", 0)):
            logger.debug(
                f"Indonesia tax calculation not enabled for slip {getattr(doc, 'name', 'unknown')}"
            )
            return

        # Calculate tax
        tax_amount = process_indonesia_taxes(doc)

        # Check if PPh 21 component exists
        pph21_component = None

        # Look for component in deductions
        if hasattr(doc, "deductions") and doc.deductions:
            for deduction in doc.deductions:
                if deduction.salary_component == "PPh 21":
                    pph21_component = deduction
                    break

        # If not found, add it
        if not pph21_component:
            if not hasattr(doc, "deductions"):
                doc.deductions = []

            pph21_component = frappe.get_doc(
                {
                    "doctype": "Salary Detail",
                    "parentfield": "deductions",
                    "parenttype": "Salary Slip",
                    "salary_component": "PPh 21",
                    "abbr": "PPh21",
                    "amount": 0,
                }
            )
            doc.append("deductions", pph21_component)
            logger.debug("Added PPh 21 component to deductions")

        # Update amount
        pph21_component.amount = tax_amount

        # Update total deductions
        if hasattr(doc, "compute_total_deductions"):
            doc.compute_total_deductions()

        # Update net pay
        if hasattr(doc, "compute_net_pay"):
            doc.compute_net_pay()

        logger.debug(f"Updated PPh 21 component with amount: {tax_amount}")

    except Exception as e:
        logger.exception(f"Error updating Indonesia tax components: {str(e)}")


def ensure_employee_tax_summary_integration(doc: Any) -> None:
    """Ensure Employee Tax Summary exists and sync it with the slip."""
    try:
        if not cint(getattr(doc, "calculate_indonesia_tax", 0)):
            return

        employee = getattr(doc, "employee", None)
        if not employee:
            return

        year, _ = get_slip_year_month(doc)

        summary_name = frappe.db.get_value(
            "Employee Tax Summary", {"employee": employee, "year": year}
        )

        created = False
        if not summary_name:
            logger.info(f"Employee Tax Summary missing for {employee}, year {year}; creating")
            summary = frappe.new_doc("Employee Tax Summary")
            summary.employee = employee
            summary.year = year
            summary.tax_method = getattr(doc, "tax_method", "Progressive")
            created = True
        else:
            summary = frappe.get_doc("Employee Tax Summary", summary_name)

        slip_tax_method = getattr(doc, "tax_method", "Progressive")
        if hasattr(summary, "tax_method") and summary.tax_method != slip_tax_method:
            logger.warning(
                f"Tax method mismatch for {employee}, year {year}: summary={summary.tax_method}, slip={slip_tax_method}"
            )
            summary.tax_method = slip_tax_method

        for field in (
            "ytd_gross_pay",
            "ytd_tax",
            "ytd_bpjs",
            "ytd_taxable_components",
            "ytd_tax_deductions",
        ):
            if hasattr(summary, field) and hasattr(doc, field):
                setattr(summary, field, flt(getattr(doc, field)))

        summary.flags.ignore_permissions = True
        summary.flags.ignore_validate_update_after_submit = True
        if created:
            summary.insert()
        else:
            summary.save()

    except Exception as e:
        logger.exception(f"Error ensuring Employee Tax Summary integration: {str(e)}")
