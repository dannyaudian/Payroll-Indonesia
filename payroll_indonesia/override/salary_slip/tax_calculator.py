# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:30:12 by dannyaudian

"""
Tax calculator module - PPh 21 (progresif & tahunan)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from payroll_indonesia.config import get_live_config
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR,
    BIAYA_JABATAN_PERCENT,
    BIAYA_JABATAN_MAX,
)

if TYPE_CHECKING:
    from frappe.model.document import Document

logger = logging.getLogger("tax_calc")


def _get_tax_brackets() -> List[Dict[str, Any]]:
    """
    Get progressive tax brackets from config.
    Returns sorted list of brackets by income_from.
    """
    cfg = get_live_config()
    brackets = cfg.get("tax", {}).get("brackets", [])
    
    if brackets:
        return sorted(brackets, key=lambda x: float(x.get("income_from", 0)))
    
    # Default tax brackets (as of 2025)
    return [
        {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
        {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
        {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
        {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
        {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
    ]


def _get_ptkp_value(tax_status: str) -> float:
    """
    Get annual PTKP (non-taxable income) value based on tax status.
    """
    cfg = get_live_config()
    ptkp_values = cfg.get("ptkp", {})
    
    if tax_status in ptkp_values:
        return float(ptkp_values[tax_status])
    
    # Default PTKP values (as of 2025)
    default_values = {
        "TK0": 54000000, "TK1": 58500000, "TK2": 63000000, "TK3": 67500000,
        "K0": 58500000, "K1": 63000000, "K2": 67500000, "K3": 72000000,
        "HB0": 112500000, "HB1": 117000000, "HB2": 121500000, "HB3": 126000000
    }
    
    return float(default_values.get(tax_status, 54000000))


def _calculate_progressive_tax(pkp: float) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Calculate PPh 21 using progressive method.
    Returns total tax and detailed breakdown per bracket.
    """
    if pkp <= 0:
        return 0.0, []
    
    brackets = _get_tax_brackets()
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
            details.append({
                "from": income_from,
                "to": income_from + remaining,
                "amount": remaining,
                "rate": rate * 100,
                "tax": tax_in_bracket
            })
            break
        
        # Middle brackets
        taxable_in_bracket = income_to - income_from
        if remaining <= taxable_in_bracket:
            tax_in_bracket = remaining * rate
            tax += tax_in_bracket
            details.append({
                "from": income_from,
                "to": income_from + remaining,
                "amount": remaining,
                "rate": rate * 100,
                "tax": tax_in_bracket
            })
            break
        else:
            tax_in_bracket = taxable_in_bracket * rate
            tax += tax_in_bracket
            details.append({
                "from": income_from,
                "to": income_to,
                "amount": taxable_in_bracket,
                "rate": rate * 100,
                "tax": tax_in_bracket
            })
            remaining -= taxable_in_bracket
    
    return tax, details


def _get_tax_status(slip: Any) -> str:
    """Extract tax status from employee document or return default."""
    employee = getattr(slip, "employee_doc", None)
    default_status = "TK0"
    
    if not employee:
        return default_status
    
    if hasattr(employee, "status_pajak") and employee.status_pajak:
        return employee.status_pajak
    
    return default_status


def _get_ytd_totals(slip: Any) -> Dict[str, float]:
    """
    Get year-to-date totals for gross pay, BPJS, and PPh 21.
    """
    # Extract year and month from slip start date
    year, month = _get_slip_year_month(slip)
    employee = getattr(slip, "employee", "unknown")
    
    logger.info(f"Fetching YTD totals for employee {employee}, {year}-{month}")
    
    # In a real implementation, this would query the database for YTD values
    # Simplified implementation for demonstration
    return {
        "gross": 0.0,
        "bpjs": 0.0,
        "pph21": 0.0
    }


def _get_slip_year_month(slip: Any) -> Tuple[int, int]:
    """Extract year and month from salary slip start date."""
    from datetime import datetime
    
    if hasattr(slip, "start_date"):
        date_parts = getattr(slip, "start_date", "").split("-")
        if len(date_parts) >= 2:
            return int(date_parts[0]), int(date_parts[1])
    
    # Default to current year and month if not found
    now = datetime.now()
    return now.year, now.month


def _is_december_calculation(slip: Any) -> bool:
    """
    Determine if this slip should use December calculation logic.
    Returns True if month is December or is_december_override flag is set.
    """
    # Check explicit override flag
    if getattr(slip, "is_december_override", 0):
        return True
    
    # Check if month is December
    _, month = _get_slip_year_month(slip)
    return month == 12


def _update_slip_fields(slip: Any, values: Dict[str, Any]) -> None:
    """Update salary slip fields with calculated values."""
    for field, value in values.items():
        if hasattr(slip, field):
            setattr(slip, field, value)


def calculate_monthly_pph_progressive(slip: Any) -> Dict[str, Any]:
    """
    Calculate PPh 21 using progressive rates for non-December months.
    """
    # Get employee tax status
    tax_status = _get_tax_status(slip)
    
    # Get income values
    gross_pay = float(getattr(slip, "gross_pay", 0))
    biaya_jabatan = min(gross_pay * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX)
    total_bpjs = float(getattr(slip, "total_bpjs", 0))
    
    # Calculate netto monthly income
    netto = gross_pay - biaya_jabatan - total_bpjs
    
    # Get PTKP value (annual)
    ptkp = _get_ptkp_value(tax_status)
    
    # Annualize income for tax calculation
    annual_netto = netto * MONTHS_PER_YEAR
    pkp = max(0, annual_netto - ptkp)
    
    # Calculate annual tax
    annual_tax, tax_details = _calculate_progressive_tax(pkp)
    
    # Calculate monthly tax
    monthly_tax = annual_tax / MONTHS_PER_YEAR
    
    # Update slip fields
    _update_slip_fields(slip, {
        "biaya_jabatan": biaya_jabatan,
        "netto": netto,
        "pph21": monthly_tax
    })
    
    # Prepare result for reporting
    result = {
        "tax_method": "PROGRESSIVE",
        "tax_status": tax_status,
        "gross_pay": gross_pay,
        "biaya_jabatan": biaya_jabatan,
        "total_bpjs": total_bpjs,
        "monthly_netto": netto,
        "annual_netto": annual_netto,
        "ptkp": ptkp,
        "pkp": pkp,
        "annual_tax": annual_tax,
        "monthly_tax": monthly_tax,
        "tax_details": tax_details
    }
    
    employee_id = getattr(slip, "employee", "unknown")
    logger.debug(f"Monthly PPh calculation for {employee_id}: {result}")
    return result


def calculate_december_pph(slip: Any) -> Dict[str, Any]:
    """
    Calculate year-end tax correction for December.
    Uses actual YTD income for more accurate annual tax calculation.
    """
    # Check if running as December (based on month or override flag)
    is_december = _is_december_calculation(slip)
    if not is_december:
        logger.info(f"Non-December month detected for {getattr(slip, 'employee', 'unknown')}, using monthly calculation")
        return calculate_monthly_pph_progressive(slip)
    
    # Get employee tax status
    tax_status = _get_tax_status(slip)
    
    # Get current income values
    current_gross = float(getattr(slip, "gross_pay", 0))
    current_bpjs = float(getattr(slip, "total_bpjs", 0))
    
    # Get YTD totals excluding current month
    ytd = _get_ytd_totals(slip)
    
    # Calculate annual totals including current month
    annual_gross = ytd.get("gross", 0) + current_gross
    annual_bpjs = ytd.get("bpjs", 0) + current_bpjs
    
    # Calculate annual biaya jabatan (capped at annual max)
    annual_biaya_jabatan = min(
        annual_gross * (BIAYA_JABATAN_PERCENT / 100),
        BIAYA_JABATAN_MAX * 12  # Annual cap
    )
    
    # Calculate annual netto
    annual_netto = annual_gross - annual_biaya_jabatan - annual_bpjs
    
    # Get PTKP value
    ptkp = _get_ptkp_value(tax_status)
    
    # Calculate PKP
    pkp = max(0, annual_netto - ptkp)
    
    # Calculate annual tax
    annual_tax, tax_details = _calculate_progressive_tax(pkp)
    
    # Calculate correction (annual tax minus YTD tax paid)
    ytd_tax_paid = ytd.get("pph21", 0)
    correction = annual_tax - ytd_tax_paid
    
    # Update slip fields
    monthly_biaya_jabatan = annual_biaya_jabatan / 12
    monthly_netto = annual_netto / 12
    
    _update_slip_fields(slip, {
        "biaya_jabatan": monthly_biaya_jabatan,
        "netto": monthly_netto,
        "koreksi_pph21": correction,
        "pph21": correction  # December tax is the correction amount
    })
    
    # Prepare result for reporting
    result = {
        "tax_method": "PROGRESSIVE_DECEMBER",
        "tax_status": tax_status,
        "current_gross": current_gross,
        "current_bpjs": current_bpjs,
        "ytd_gross": ytd.get("gross", 0),
        "ytd_bpjs": ytd.get("bpjs", 0),
        "ytd_tax_paid": ytd_tax_paid,
        "annual_gross": annual_gross,
        "annual_bpjs": annual_bpjs,
        "annual_biaya_jabatan": annual_biaya_jabatan,
        "annual_netto": annual_netto,
        "ptkp": ptkp,
        "pkp": pkp,
        "annual_tax": annual_tax,
        "correction": correction,
        "tax_details": tax_details,
        "is_december_override": getattr(slip, "is_december_override", 0)
    }
    
    employee_id = getattr(slip, "employee", "unknown")
    logger.debug(f"December PPh calculation for {employee_id}: {result}")
    return result
