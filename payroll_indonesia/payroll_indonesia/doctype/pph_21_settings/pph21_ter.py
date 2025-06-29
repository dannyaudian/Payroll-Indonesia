# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 00:09:31 by dannyaudian

"""
PPh 21 TER (Tarif Efektif Rata-rata) utility functions.

Handles TER rate retrieval and category mapping for PPh 21 tax calculations
based on PMK 168/2023 regulations.
"""

import logging
from bisect import bisect_right
from typing import Dict, List, Union, Optional, Any, Tuple

import frappe
from frappe import _
from frappe.utils import flt

from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.frappe_helpers import safe_execute

# Configure logger
logger = logging.getLogger("payroll_indonesia.tax")

# Cache for TER rates to avoid repeated config lookups
# Format: {ter_category: [(income_from, income_to, rate, is_highest)]}
_ter_rate_cache: Dict[str, List[Tuple[float, float, float, bool]]] = {}

# PTKP to TER category mapping cache
_ter_category_cache: Dict[str, str] = {}


@safe_execute(default_value=0.0, log_exception=True)
def get_ter_rate(ptkp_code: str, taxable_income: float) -> float:
    """
    Get TER rate for a specific PTKP status and income level.
    
    Args:
        ptkp_code: Tax status code (e.g. 'TK0', 'K1')
        taxable_income: Monthly gross income amount
        
    Returns:
        float: TER rate as decimal (e.g., 0.05 for 5%)
    """
    # Ensure valid inputs
    if not ptkp_code:
        logger.warning("Empty PTKP code provided, defaulting to TK0")
        ptkp_code = "TK0"
        
    taxable_income = flt(taxable_income)
    if taxable_income < 0:
        logger.warning(f"Negative income {taxable_income} provided, using absolute value")
        taxable_income = abs(taxable_income)
    
    # Map PTKP status to TER category
    ter_category = get_ter_category(ptkp_code)
    
    # Get TER rates for this category
    rates = _get_ter_rates_for_category(ter_category)
    
    # Fast path: no rates or zero income
    if not rates or taxable_income == 0:
        logger.info(f"No rates found for {ter_category} or zero income")
        return 0.0
    
    # Find applicable rate using binary search for efficiency
    return _find_applicable_rate(rates, taxable_income)


@safe_execute(default_value="TER C", log_exception=True)
def get_ter_category(ptkp_code: str) -> str:
    """
    Map PTKP status to TER category based on PMK 168/2023.
    
    Args:
        ptkp_code: PTKP status code (e.g., 'TK0', 'K1')
        
    Returns:
        str: TER category ('TER A', 'TER B', or 'TER C')
    """
    # Check cache first
    if ptkp_code in _ter_category_cache:
        return _ter_category_cache[ptkp_code]
    
    # Get mapping from config
    config = get_live_config()
    ptkp_ter_mapping = config.get("ptkp_to_ter_mapping", {})
    
    # If mapping exists in config, use it
    if ptkp_code in ptkp_ter_mapping:
        category = ptkp_ter_mapping[ptkp_code]
        _ter_category_cache[ptkp_code] = category
        return category
    
    # Fallback mapping based on tax regulations
    if ptkp_code in ("TK0", "TK1"):
        category = "TER A"
    elif ptkp_code == "K0":
        category = "TER B"
    else:
        # Higher PTKP categories (K1, TK2, K2, TK3, K3, HB*)
        category = "TER C"
    
    # Cache result for future lookups
    _ter_category_cache[ptkp_code] = category
    return category


def _get_ter_rates_for_category(ter_category: str) -> List[Tuple[float, float, float, bool]]:
    """
    Get TER rates for a specific category, with caching for performance.
    
    Args:
        ter_category: TER category ('TER A', 'TER B', or 'TER C')
        
    Returns:
        list: List of (income_from, income_to, rate, is_highest) tuples
    """
    # Check cache first
    if ter_category in _ter_rate_cache:
        return _ter_rate_cache[ter_category]
    
    # Get rates from configuration
    config = get_live_config()
    ter_rates = config.get("ter_rates", {})
    
    # If category not in config, return empty list
    if ter_category not in ter_rates:
        logger.warning(f"No TER rates found for category {ter_category}")
        _ter_rate_cache[ter_category] = []
        return []
    
    # Process and sort rates for this category
    category_rates = []
    for rate_data in ter_rates[ter_category]:
        income_from = flt(rate_data.get("income_from", 0))
        income_to = flt(rate_data.get("income_to", 0))
        rate = flt(rate_data.get("rate", 0)) / 100.0  # Convert percentage to decimal
        is_highest = bool(rate_data.get("is_highest_bracket", False))
        
        category_rates.append((income_from, income_to, rate, is_highest))
    
    # Sort by income_from for binary search
    category_rates.sort(key=lambda x: x[0])
    
    # Cache for future lookups
    _ter_rate_cache[ter_category] = category_rates
    return category_rates


def _find_applicable_rate(
    rates: List[Tuple[float, float, float, bool]], 
    income: float
) -> float:
    """
    Find the applicable TER rate for the given income using binary search.
    
    Args:
        rates: List of (income_from, income_to, rate, is_highest) tuples
        income: Monthly gross income
        
    Returns:
        float: Applicable TER rate as decimal
    """
    # Extract income_from values for binary search
    income_thresholds = [r[0] for r in rates]
    
    # Find the index of the first bracket with income_from > income
    idx = bisect_right(income_thresholds, income)
    
    # Adjust to get the last bracket with income_from <= income
    if idx > 0:
        idx -= 1
    
    # Check if we have a valid bracket
    if idx < len(rates):
        income_from, income_to, rate, is_highest = rates[idx]
        
        # Check if income is within bracket range
        if income >= income_from and (income_to == 0 or income < income_to or is_highest):
            return rate
    
    # If no bracket matches, return 0
    return 0.0


def clear_cache() -> None:
    """Clear all TER rate caches."""
    global _ter_rate_cache, _ter_category_cache
    _ter_rate_cache.clear()
    _ter_category_cache.clear()


def get_default_ter_rates() -> Dict[str, List[Dict[str, Any]]]:
    """
    Get default TER rates based on PMK 168/2023.
    
    Returns:
        dict: Dictionary of TER rates by category
    """
    # Retrieve from configuration if available
    config = get_live_config()
    if "ter_rates" in config:
        return config["ter_rates"]
    
    # Return empty dict if not found
    return {}
