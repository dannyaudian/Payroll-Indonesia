# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 by dannyaudian

"""
Tax calculator module - PPh 21 (progresif & tahunan)
"""

import logging
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime

import frappe
from frappe.utils import flt, cint, getdate

from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.frappe_helpers import logger
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR,
    BIAYA_JABATAN_PERCENT,
    BIAYA_JABATAN_MAX,
)

__all__ = [
    "get_tax_brackets",
    "get_ptkp_value",
    "calculate_progressive_tax",
    "get_tax_status",
    "get_ytd_totals",
    "get_slip_year_month",
    "is_december_calculation",
    "update_slip_fields",
    "calculate_monthly_pph_progressive",
    "calculate_december_pph",
]


def get_tax_brackets() -> List[Dict[str, Any]]:
    """
    Get progressive tax brackets from config.
    Returns sorted list of brackets by income_from.
    """
    try:
        cfg = get_live_config()
        brackets = cfg.get("tax", {}).get("brackets", [])

        if brackets:
            return sorted(brackets, key=lambda x: float(x.get("income_from", 0)))

        # Default tax brackets (as of 2025)
        default_brackets = [
            {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
            {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
            {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
            {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
            {"income_from": 5000000000, "income_to": 0, "tax_rate": 35},
        ]
        logger.warning("No tax brackets found in config. Using default brackets.")
        return default_brackets

    except Exception as e:
        logger.exception(f"Error getting tax brackets: {str(e)}")
        # Return default brackets on error
        return [
            {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
            {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
            {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
            {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
            {"income_from": 5000000000, "income_to": 0, "tax_rate": 35},
        ]


def get_ptkp_value(tax_status: str) -> float:
    """
    Get annual PTKP (non-taxable income) value based on tax status.
    
    Args:
        tax_status: Tax status code (e.g., TK0, K1)
        
    Returns:
        float: Annual PTKP amount
    """
    try:
        if not tax_status:
            logger.warning("Empty tax status provided. Using default TK0.")
            tax_status = "TK0"
            
        cfg = get_live_config()
        ptkp_values = cfg.get("ptkp", {})

        if tax_status in ptkp_values:
            return float(ptkp_values[tax_status])

        # Default PTKP values (as of 2025)
        default_values = {
            "TK0": 54000000,
            "TK1": 58500000,
            "TK2": 63000000,
            "TK3": 67500000,
            "K0": 58500000,
            "K1": 63000000,
            "K2": 67500000,
            "K3": 72000000,
            "HB0": 112500000,
            "HB1": 117000000,
            "HB2": 121500000,
            "HB3": 126000000,
        }

        if tax_status not in default_values:
            logger.warning(f"Unknown tax status: {tax_status}. Using TK0 as default.")
            tax_status = "TK0"
            
        return float(default_values.get(tax_status, 54000000))
        
    except Exception as e:
        logger.exception(f"Error getting PTKP value for {tax_status}: {str(e)}")
        # Return default TK0 value on error
        return 54000000


def calculate_progressive_tax(pkp: float) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Calculate PPh 21 using progressive method.
    
    Args:
        pkp: Penghasilan Kena Pajak (taxable income)
        
    Returns:
        Tuple[float, List[Dict[str, Any]]]: Total tax and detailed breakdown per bracket
    """
    try:
        if pkp <= 0:
            return 0.0, []

        brackets = get_tax_brackets()
        tax = 0.0
        details = []
        remaining = pkp

        for bracket in brackets:
            income_from = float(bracket.get("income_from", 0))
            income_to = float(bracket.get("income_to", 0))
            rate = float(bracket.get("tax_rate", 0)) / 100.0

            # Handle top bracket (no upper limit)
            if income_to == 0 or income_to > remaining + income_from:
                tax_in_bracket = remaining * rate
                tax += tax_in_bracket
                details.append(
                    {
                        "from": income_from,
                        "to": income_from + remaining,
                        "amount": remaining,
                        "rate": rate * 100,
                        "tax": tax_in_bracket,
                    }
                )
                break

            # Middle brackets
            taxable_in_bracket = income_to - income_from
            if remaining <= taxable_in_bracket:
                tax_in_bracket = remaining * rate
                tax += tax_in_bracket
                details.append(
                    {
                        "from": income_from,
                        "to": income_from + remaining,
                        "amount": remaining,
                        "rate": rate * 100,
                        "tax": tax_in_bracket,
                    }
                )
                break
            else:
                tax_in_bracket = taxable_in_bracket * rate
                tax += tax_in_bracket
                details.append(
                    {
                        "from": income_from,
                        "to": income_to,
                        "amount": taxable_in_bracket,
                        "rate": rate * 100,
                        "tax": tax_in_bracket,
                    }
                )
                remaining -= taxable_in_bracket

        return tax, details
        
    except Exception as e:
        logger.exception(f"Error calculating progressive tax for PKP {pkp}: {str(e)}")
        # Return zero on error
        return 0.0, []


def get_tax_status(slip: Any) -> str:
    """
    Extract tax status from employee document or return default.
    
    Args:
        slip: The Salary Slip document
        
    Returns:
        str: Tax status code (e.g., TK0, K1)
    """
    try:
        default_status = "TK0"
        
        # Try to get from employee_doc field
        employee = getattr(slip, "employee_doc", None)
        if employee and hasattr(employee, "status_pajak") and employee.status_pajak:
            return employee.status_pajak
            
        # If employee_doc not available, try to get directly from employee
        if hasattr(slip, "employee") and slip.employee:
            try:
                employee_id = slip.employee
                employee_doc = frappe.get_doc("Employee", employee_id)
                if hasattr(employee_doc, "status_pajak") and employee_doc.status_pajak:
                    # Set employee_doc for future reference
                    slip.employee_doc = employee_doc
                    return employee_doc.status_pajak
            except Exception as e:
                logger.warning(f"Could not load employee {getattr(slip, 'employee', 'unknown')}: {e}")
                
        # If we got here, use default
        logger.warning(
            f"No tax status found for employee {getattr(slip, 'employee', 'unknown')}. "
            f"Using default: {default_status}"
        )
        return default_status
        
    except Exception as e:
        logger.exception(f"Error getting tax status: {str(e)}")
        return "TK0"


def get_ytd_totals(slip: Any) -> Dict[str, float]:
    """
    Get year-to-date totals for gross pay, BPJS, and PPh 21.
    Aggregates data from all salary slips in the same fiscal year up to the slip's posting date.

    Args:
        slip: The salary slip object

    Returns:
        Dictionary with YTD totals for gross, bpjs, and pph21
    """
    try:
        year, _ = get_slip_year_month(slip)
        employee = getattr(slip, "employee", None)
        posting_date = getattr(slip, "posting_date", None)
        slip_name = getattr(slip, "name", "unknown")

        if not employee or not posting_date:
            logger.warning(f"Missing employee or posting_date in slip {slip_name}, returning zeros")
            return {"gross": 0.0, "bpjs": 0.0, "pph21": 0.0}

        logger.debug(f"Fetching YTD totals for employee {employee}, year {year}")

        # Check cache first
        cache_key = f"ytd_totals:{employee}:{year}:{posting_date}"
        cached_result = frappe.cache().get_value(cache_key)
        if cached_result:
            logger.debug(f"Using cached YTD totals for {employee}")
            return cached_result

        # Default result if no data is found
        result = {"gross": 0.0, "bpjs": 0.0, "pph21": 0.0}

        # Build fields list based on available columns
        select_fields = []
        field_mappings = {
            "gross_pay": "gross",
            "base_gross_pay": "gross",
            "total_bpjs": "bpjs",
            "bpjs_amount": "bpjs",
            "base_bpjs": "bpjs",
            "pph21": "pph21",
            "pph21_tax": "pph21",
            "base_pph21": "pph21",
        }

        for db_field, result_field in field_mappings.items():
            if frappe.db.has_column("Salary Slip", db_field):
                select_fields.append(f"SUM(`{db_field}`) as {result_field}")

        if not select_fields:
            logger.warning("No matching columns found in Salary Slip table")
            return result

        # Query for YTD totals (excluding current slip)
        ytd_data = frappe.db.sql(
            f"""
            SELECT {', '.join(select_fields)}
            FROM `tabSalary Slip`
            WHERE docstatus = 1
              AND employee = %s
              AND posting_date <= %s
              AND YEAR(posting_date) = %s
              AND name != %s
            """,
            (employee, posting_date, year, slip_name),
            as_dict=1,
        )

        if ytd_data and len(ytd_data) > 0:
            # Update result with non-null values from query
            for key in result.keys():
                if key in ytd_data[0] and ytd_data[0][key] is not None:
                    result[key] = flt(ytd_data[0][key])

        # Cache the result
        frappe.cache().set_value(cache_key, result, expires_in_sec=300)
        
        logger.debug(f"YTD totals for {employee}: {result}")
        return result

    except Exception as e:
        logger.exception(f"Error calculating YTD totals: {str(e)}")
        return {"gross": 0.0, "bpjs": 0.0, "pph21": 0.0}


def get_slip_year_month(slip: Any) -> Tuple[int, int]:
    """
    Extract year and month from salary slip start date.
    
    Args:
        slip: The Salary Slip document
        
    Returns:
        Tuple[int, int]: Year and month
    """
    try:
        # Try to get from start_date
        if hasattr(slip, "start_date") and slip.start_date:
            date_obj = getdate(slip.start_date)
            return date_obj.year, date_obj.month
            
        # Try to get from posting_date
        if hasattr(slip, "posting_date") and slip.posting_date:
            date_obj = getdate(slip.posting_date)
            return date_obj.year, date_obj.month

        # Default to current year and month if not found
        now = datetime.now()
        logger.warning(
            f"No date found in slip {getattr(slip, 'name', 'unknown')}. "
            f"Using current date: {now.year}-{now.month}"
        )
        return now.year, now.month
        
    except Exception as e:
        logger.exception(f"Error getting slip year/month: {str(e)}")
        now = datetime.now()
        return now.year, now.month


def is_december_calculation(slip: Any) -> bool:
    """
    Determine if this slip should use December calculation logic.
    
    Args:
        slip: The Salary Slip document
        
    Returns:
        bool: True if month is December or is_december_override flag is set
    """
    try:
        # Check explicit override flag
        if cint(getattr(slip, "is_december_override", 0)) == 1:
            logger.debug(f"December override flag set for slip {getattr(slip, 'name', 'unknown')}")
            return True

        # Check if month is December
        _, month = get_slip_year_month(slip)
        is_dec = month == 12
        
        if is_dec:
            logger.debug(f"December month detected for slip {getattr(slip, 'name', 'unknown')}")
            
        return is_dec
        
    except Exception as e:
        logger.exception(f"Error checking December calculation: {str(e)}")
        return False


def update_slip_fields(slip: Any, values: Dict[str, Any]) -> None:
    """
    Update salary slip fields with calculated values.
    
    Args:
        slip: The Salary Slip document
        values: Dictionary of field name/value pairs to update
    """
    try:
        for field, value in values.items():
            if hasattr(slip, field):
                setattr(slip, field, value)
                logger.debug(f"Updated {field}={value} in slip {getattr(slip, 'name', 'unknown')}")
            else:
                logger.warning(
                    f"Field {field} not found in slip {getattr(slip, 'name', 'unknown')}"
                )
                
    except Exception as e:
        logger.exception(f"Error updating slip fields: {str(e)}")


def calculate_monthly_pph_progressive(slip: Any) -> Dict[str, Any]:
    """
    Calculate PPh 21 using progressive rates for non-December months.
    
    Args:
        slip: The Salary Slip document
        
    Returns:
        Dict[str, Any]: Calculation results
    """
    try:
        # Initialize result with zeros
        result = {
            "tax_method": "PROGRESSIVE",
            "tax_status": "TK0",
            "gross_pay": 0.0,
            "biaya_jabatan": 0.0,
            "total_bpjs": 0.0,
            "monthly_netto": 0.0,
            "annual_netto": 0.0,
            "ptkp": 0.0,
            "pkp": 0.0,
            "annual_tax": 0.0,
            "monthly_tax": 0.0,
            "tax_details": [],
        }
        
        # Get tax status
        tax_status = get_tax_status(slip)
        result["tax_status"] = tax_status
        
        # Get gross pay
        gross_pay = flt(getattr(slip, "gross_pay", 0))
        if gross_pay <= 0:
            logger.warning(f"Zero or negative gross pay for slip {getattr(slip, 'name', 'unknown')}")
            
        result["gross_pay"] = gross_pay
        
        # Calculate biaya jabatan
        biaya_jabatan = min(gross_pay * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX)
        result["biaya_jabatan"] = biaya_jabatan
        
        # Get total BPJS employee
        total_bpjs = flt(getattr(slip, "total_bpjs", 0))
        result["total_bpjs"] = total_bpjs
        
        # Calculate netto
        netto = gross_pay - biaya_jabatan - total_bpjs
        result["monthly_netto"] = netto
        
        # Calculate annual values
        annual_netto = netto * MONTHS_PER_YEAR
        result["annual_netto"] = annual_netto
        
        # Get PTKP
        ptkp = get_ptkp_value(tax_status)
        result["ptkp"] = ptkp
        
        # Calculate PKP
        pkp = max(0, annual_netto - ptkp)
        result["pkp"] = pkp
        
        # Calculate tax
        annual_tax, tax_details = calculate_progressive_tax(pkp)
        result["annual_tax"] = annual_tax
        result["tax_details"] = tax_details
        
        # Calculate monthly tax
        monthly_tax = annual_tax / MONTHS_PER_YEAR
        result["monthly_tax"] = monthly_tax
        
        # Update slip fields
        update_slip_fields(
            slip, 
            {
                "biaya_jabatan": biaya_jabatan, 
                "netto": netto, 
                "pph21": monthly_tax
            }
        )
        
        # Also update any PPh 21 component
        _update_pph21_component(slip, monthly_tax)

        employee_id = getattr(slip, "employee", "unknown")
        logger.debug(f"Monthly PPh calculation for {employee_id}: {result}")
        return result
        
    except Exception as e:
        logger.exception(f"Error calculating monthly PPh: {str(e)}")
        # Set fields to zero in case of error
        update_slip_fields(
            slip, 
            {
                "biaya_jabatan": 0, 
                "netto": 0, 
                "pph21": 0
            }
        )
        return {
            "tax_method": "PROGRESSIVE",
            "tax_status": get_tax_status(slip),
            "gross_pay": flt(getattr(slip, "gross_pay", 0)),
            "biaya_jabatan": 0,
            "total_bpjs": 0,
            "monthly_netto": 0,
            "annual_netto": 0,
            "ptkp": 0,
            "pkp": 0,
            "annual_tax": 0,
            "monthly_tax": 0,
            "tax_details": [],
            "error": str(e)
        }


def calculate_december_pph(slip: Any) -> Dict[str, Any]:
    """
    Calculate year-end tax correction for December.
    Uses actual YTD income for more accurate annual tax calculation.
    
    Args:
        slip: The Salary Slip document
        
    Returns:
        Dict[str, Any]: Calculation results
    """
    try:
        is_december = is_december_calculation(slip)
        if not is_december:
            logger.info(
                f"Non-December month detected for {getattr(slip, 'employee', 'unknown')}, "
                f"using monthly calculation"
            )
            return calculate_monthly_pph_progressive(slip)

        # Initialize result with zeros
        result = {
            "tax_method": "PROGRESSIVE_DECEMBER",
            "tax_status": "TK0",
            "current_gross": 0.0,
            "current_bpjs": 0.0,
            "ytd_gross": 0.0,
            "ytd_bpjs": 0.0,
            "ytd_tax_paid": 0.0,
            "annual_gross": 0.0,
            "annual_bpjs": 0.0,
            "annual_biaya_jabatan": 0.0,
            "annual_netto": 0.0,
            "ptkp": 0.0,
            "pkp": 0.0,
            "annual_tax": 0.0,
            "correction": 0.0,
            "tax_details": [],
            "is_december_override": 0,
        }
        
        # Get tax status
        tax_status = get_tax_status(slip)
        result["tax_status"] = tax_status
        
        # Get current values
        current_gross = flt(getattr(slip, "gross_pay", 0))
        current_bpjs = flt(getattr(slip, "total_bpjs", 0))
        result["current_gross"] = current_gross
        result["current_bpjs"] = current_bpjs
        
        # Get YTD values
        ytd = get_ytd_totals(slip)
        result["ytd_gross"] = ytd.get("gross", 0)
        result["ytd_bpjs"] = ytd.get("bpjs", 0)
        result["ytd_tax_paid"] = ytd.get("pph21", 0)
        
        # Calculate annual values
        annual_gross = ytd.get("gross", 0) + current_gross
        annual_bpjs = ytd.get("bpjs", 0) + current_bpjs
        result["annual_gross"] = annual_gross
        result["annual_bpjs"] = annual_bpjs
        
        # Calculate annual biaya jabatan
        annual_biaya_jabatan = min(
            annual_gross * (BIAYA_JABATAN_PERCENT / 100), 
            BIAYA_JABATAN_MAX * 12
        )
        result["annual_biaya_jabatan"] = annual_biaya_jabatan
        
        # Calculate annual netto
        annual_netto = annual_gross - annual_biaya_jabatan - annual_bpjs
        result["annual_netto"] = annual_netto
        
        # Get PTKP
        ptkp = get_ptkp_value(tax_status)
        result["ptkp"] = ptkp
        
        # Calculate PKP
        pkp = max(0, annual_netto - ptkp)
        result["pkp"] = pkp
        
        # Calculate tax
        annual_tax, tax_details = calculate_progressive_tax(pkp)
        result["annual_tax"] = annual_tax
        result["tax_details"] = tax_details
        
        # Calculate correction
        ytd_tax_paid = ytd.get("pph21", 0)
        correction = annual_tax - ytd_tax_paid
        result["correction"] = correction
        
        # Calculate monthly values for display
        monthly_biaya_jabatan = annual_biaya_jabatan / 12
        monthly_netto = annual_netto / 12
        
        # Set December override flag
        result["is_december_override"] = cint(getattr(slip, "is_december_override", 0))
        
        # Update slip fields
        update_slip_fields(
            slip,
            {
                "biaya_jabatan": monthly_biaya_jabatan,
                "netto": monthly_netto,
                "koreksi_pph21": correction,
                "pph21": correction,
            },
        )
        
        # Also update any PPh 21 component
        _update_pph21_component(slip, correction)

        employee_id = getattr(slip, "employee", "unknown")
        logger.debug(f"December PPh calculation for {employee_id}: {result}")
        return result
        
    except Exception as e:
        logger.exception(f"Error calculating December PPh: {str(e)}")
        # Set fields to zero in case of error
        update_slip_fields(
            slip,
            {
                "biaya_jabatan": 0,
                "netto": 0,
                "koreksi_pph21": 0,
                "pph21": 0,
            },
        )
        return {
            "tax_method": "PROGRESSIVE_DECEMBER",
            "tax_status": get_tax_status(slip),
            "current_gross": flt(getattr(slip, "gross_pay", 0)),
            "current_bpjs": flt(getattr(slip, "total_bpjs", 0)),
            "ytd_gross": 0,
            "ytd_bpjs": 0,
            "ytd_tax_paid": 0,
            "annual_gross": 0,
            "annual_bpjs": 0,
            "annual_biaya_jabatan": 0,
            "annual_netto": 0,
            "ptkp": 0,
            "pkp": 0,
            "annual_tax": 0,
            "correction": 0,
            "tax_details": [],
            "is_december_override": cint(getattr(slip, "is_december_override", 0)),
            "error": str(e)
        }


def _update_pph21_component(slip: Any, tax_amount: float) -> None:
    """
    Update PPh 21 component in deductions.
    
    Args:
        slip: The Salary Slip document
        tax_amount: The tax amount to set
    """
    try:
        if not hasattr(slip, "deductions"):
            return
            
        for deduction in slip.deductions:
            if getattr(deduction, "salary_component", "") == "PPh 21":
                deduction.amount = tax_amount
                logger.debug(
                    f"Updated PPh 21 component to {tax_amount} in slip {getattr(slip, 'name', 'unknown')}"
                )
                break
                
    except Exception as e:
        logger.exception(f"Error updating PPh 21 component: {str(e)}")
