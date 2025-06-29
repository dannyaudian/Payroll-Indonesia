# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 01:15:16 by dannyaudian

"""
Tax calculator module - PPh 21 (progressive & annual)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, cast, TYPE_CHECKING

from payroll_indonesia.config import get_live_config
from payroll_indonesia.constants import (
    MONTHS_PER_YEAR,
    BIAYA_JABATAN_PERCENT,
    BIAYA_JABATAN_MAX,
)

if TYPE_CHECKING:
    from frappe.model.document import Document

logger = logging.getLogger("tax_calc")


def get_tax_brackets(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Get progressive tax brackets from config.
    """
    brackets = cfg.get("tax_brackets", [])
    if brackets:
        # Sort by income_from to ensure proper order
        return sorted(brackets, key=lambda x: x.get("income_from", 0))
    
    # Default tax brackets (as of 2025)
    return [
        {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
        {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
        {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
        {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
        {"income_from": 5000000000, "income_to": 0, "tax_rate": 35}
    ]


def get_ptkp_value(tax_status: str, cfg: Dict[str, Any]) -> float:
    """
    Get annual PTKP (non-taxable income) value based on tax status.
    """
    ptkp_values = cfg.get("ptkp", {})
    
    # If tax status exists in configuration, use that value
    if tax_status in ptkp_values:
        return float(ptkp_values[tax_status])
    
    # Default PTKP values (as of 2025)
    default_values = {
        "TK0": 54000000, "TK1": 58500000, "TK2": 63000000, "TK3": 67500000,
        "K0": 58500000, "K1": 63000000, "K2": 67500000, "K3": 72000000,
        "HB0": 112500000, "HB1": 117000000, "HB2": 121500000, "HB3": 126000000
    }
    
    return float(default_values.get(tax_status, 54000000))


def calculate_progressive_tax(pkp: float, brackets: List[Dict[str, Any]]) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Calculate PPh 21 using progressive method.
    Returns total tax and detailed breakdown per bracket.
    """
    if pkp <= 0:
        return 0.0, []
    
    tax = 0.0
    details = []
    remaining = pkp
    
    for bracket in brackets:
        income_from = float(bracket.get("income_from", 0))
        income_to = float(bracket.get("income_to", 0))
        rate = float(bracket.get("tax_rate", 0)) / 100.0
        
        # Handle top bracket (no upper limit)
        if income_to == 0 or income_to > remaining:
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


def get_ytd_totals(slip: Any, year: int, month: int) -> Dict[str, float]:
    """
    Get year-to-date totals for gross pay, BPJS, and PPh 21.
    """
    # In a real implementation, this would query the database for YTD values
    # Simplified for demonstration purposes
    employee = getattr(slip, "employee", "")
    
    logger.info(f"Fetching YTD totals for employee {employee}, {year}-{month}")
    
    # Return default values for demonstration
    return {
        "gross": 0.0,
        "bpjs": 0.0,
        "pph21": 0.0
    }


def should_run_as_december(slip: Any) -> bool:
    """
    Determine if a salary slip should use December calculation logic.
    Returns True if is_december_override flag is set to 1.
    """
    return bool(getattr(slip, "is_december_override", 0))


def calculate_monthly_pph_progressive(slip: Any) -> Dict[str, Any]:
    """
    Calculate PPh 21 using progressive rates for non-December months.
    """
    cfg = get_live_config()
    
    # Get employee tax status
    employee = getattr(slip, "employee_doc", None)
    tax_status = "TK0"  # Default
    if employee and hasattr(employee, "status_pajak") and employee.status_pajak:
        tax_status = employee.status_pajak
    
    # Get income values
    gross_pay = float(getattr(slip, "gross_pay", 0))
    biaya_jabatan = min(gross_pay * (BIAYA_JABATAN_PERCENT / 100), BIAYA_JABATAN_MAX)
    total_bpjs = float(getattr(slip, "total_bpjs", 0))
    
    # Calculate netto monthly income
    netto = gross_pay - biaya_jabatan - total_bpjs
    
    # Get PTKP value (annual)
    ptkp = get_ptkp_value(tax_status, cfg)
    
    # Annualize income for tax calculation
    annual_netto = netto * MONTHS_PER_YEAR
    pkp = max(0, annual_netto - ptkp)
    
    # Calculate annual tax
    tax_brackets = get_tax_brackets(cfg)
    annual_tax, tax_details = calculate_progressive_tax(pkp, tax_brackets)
    
    # Calculate monthly tax
    monthly_tax = annual_tax / MONTHS_PER_YEAR
    
    # Store values in salary slip
    if hasattr(slip, "biaya_jabatan"):
        slip.biaya_jabatan = biaya_jabatan
    if hasattr(slip, "netto"):
        slip.netto = netto
    
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
    
    logger.debug(f"Monthly PPh calculation for {getattr(slip, 'employee', '')}: {result}")
    return result


def calculate_december_pph(slip: Any) -> Dict[str, Any]:
    """
    Calculate year-end tax correction for December as per PMK 168/2023.
    Uses is_december_override flag to handle non-December months that need
    December correction calculation.
    """
    cfg = get_live_config()
    
    # Check if running as December (based on is_december_override flag)
    is_dec_override = should_run_as_december(slip)
    if is_dec_override:
        logger.info(f"Running December PPh calculation for {getattr(slip, 'employee', '')} (is_december_override=1)")
    
    # Get employee tax status
    employee = getattr(slip, "employee_doc", None)
    tax_status = "TK0"  # Default
    if employee and hasattr(employee, "status_pajak") and employee.status_pajak:
        tax_status = employee.status_pajak
    
    # Get current income values
    current_gross = float(getattr(slip, "gross_pay", 0))
    current_bpjs = float(getattr(slip, "total_bpjs", 0))
    
    # Get start date details to determine year and month
    from datetime import datetime
    if hasattr(slip, "start_date"):
        date_parts = getattr(slip, "start_date", "").split("-")
        if len(date_parts) >= 2:
            year = int(date_parts[0])
            month = int(date_parts[1])
        else:
            year = datetime.now().year
            month = 12
    else:
        year = datetime.now().year
        month = 12
    
    # Get YTD totals excluding current month
    ytd = get_ytd_totals(slip, year, month)
    
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
    ptkp = get_ptkp_value(tax_status, cfg)
    
    # Calculate PKP
    pkp = max(0, annual_netto - ptkp)
    
    # Calculate annual tax
    tax_brackets = get_tax_brackets(cfg)
    annual_tax, tax_details = calculate_progressive_tax(pkp, tax_brackets)
    
    # Calculate correction (annual tax minus YTD tax paid)
    ytd_tax_paid = ytd.get("pph21", 0)
    correction = annual_tax - ytd_tax_paid
    
    # Store values in salary slip
    if hasattr(slip, "biaya_jabatan"):
        slip.biaya_jabatan = annual_biaya_jabatan / 12  # Monthly value
    if hasattr(slip, "netto"):
        slip.netto = annual_netto / 12  # Monthly value
    if hasattr(slip, "koreksi_pph21"):
        slip.koreksi_pph21 = correction
    
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
        "is_december_override": is_dec_override
    }
    
    logger.debug(f"December PPh calculation for {getattr(slip, 'employee', '')}: {result}")
    return result
