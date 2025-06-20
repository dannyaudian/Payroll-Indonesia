# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Tax Functions for TER (Tarif Efektif Rata-rata) Method
as per PMK 168/PMK.010/2023.

This module serves as the single source of truth for TER calculations,
providing stable APIs for tax rate retrieval and category mapping.

TER is a simplified tax calculation method used for Indonesian PPh 21 income tax.
Instead of calculating annual tax with progressive rates and dividing by 12,
it directly applies an effective rate to monthly income.
"""

from __future__ import annotations

import functools
import json
from typing import List, Optional, Tuple, Union

import frappe
from frappe.utils import flt

__all__ = ["get_ter_rate", "map_ptkp_to_ter_category", "validate_ter_data_availability"]

# Constants for TER categories
TER_CATEGORY_A = "TER A"
TER_CATEGORY_B = "TER B"
TER_CATEGORY_C = "TER C"
TER_CATEGORIES = [TER_CATEGORY_A, TER_CATEGORY_B, TER_CATEGORY_C]

# Default rates by category based on PMK 168/2023
# These are absolute last-resort values used if all other lookups fail
DEFAULT_TER_RATES = {
    TER_CATEGORY_A: 0.05,  # 5% for TER A
    TER_CATEGORY_B: 0.15,  # 15% for TER B
    TER_CATEGORY_C: 0.25,  # 25% for TER C
    "": 0.25,  # Default for empty category
}

# Initialize logger
logger = frappe.logger("payroll_indonesia.payroll_indonesia.tax")


def normalize_ter_category(category: str) -> str:
    """
    Normalize the TER category input to standard format.

    Args:
        category: TER category (can be 'A', 'B', 'C', 'TER A', 'TER B', 'TER C')

    Returns:
        str: Normalized TER category ('TER A', 'TER B', or 'TER C')
    """
    if not category:
        return TER_CATEGORY_C

    category = category.strip().upper()

    # Handle short format conversion (A, B, C) to full format (TER A, TER B, TER C)
    if category in ["A", "B", "C"]:
        category = f"TER {category}"
    elif not category.startswith("TER "):
        return TER_CATEGORY_C

    # Validate against allowed categories
    if category not in TER_CATEGORIES:
        return TER_CATEGORY_C

    return category


@functools.lru_cache(maxsize=128)
def get_ter_rate(category: str, income: Union[float, int]) -> float:
    """
    Get the TER (Tarif Efektif Rata-rata) rate for a given category and income level.

    Implements a hierarchical lookup strategy:
    1. Query DocType 'PPh 21 TER Table' for matching category & income range.
    2. If not found, read defaults from settings.
    3. As a final fallback, use hard-coded DEFAULT_TER_RATES.

    Args:
        category: TER category ('A', 'B', 'C', 'TER A', 'TER B', 'TER C')
        income: Monthly income amount

    Returns:
        float: The TER rate as decimal (e.g., 0.05 for 5%)

    Raises:
        ValueError: If inputs are invalid
    """
    # Input validation
    if income is None:
        raise ValueError("Income cannot be None")

    try:
        income_value = flt(income)
        if income_value < 0:
            raise ValueError("Income cannot be negative")
    except (ValueError, TypeError):
        raise ValueError(f"Invalid income value: {income}")

    # No tax for zero income
    if income_value == 0:
        return 0.0

    # Normalize category
    normalized_category = normalize_ter_category(category)

    # Lookup Strategy 1: Query database table
    rate = _get_ter_rate_from_database(normalized_category, income_value)
    if rate is not None:
        logger.info(
            f"TER rate {rate} found in database for {normalized_category}, income {income_value}"
        )
        return rate

    # Lookup Strategy 2: Get from settings JSON
    rate = _get_ter_rate_from_settings(normalized_category, income_value)
    if rate is not None:
        logger.info(
            f"TER rate {rate} found in settings for {normalized_category}, income {income_value}"
        )
        return rate

    # Lookup Strategy 3: Use hard-coded defaults
    rate = DEFAULT_TER_RATES.get(normalized_category, DEFAULT_TER_RATES[TER_CATEGORY_C])
    logger.info(f"Using default TER rate {rate} for {normalized_category}, income {income_value}")
    return rate


def _get_ter_rate_from_database(category: str, income: float) -> Optional[float]:
    """
    Get TER rate from PPh 21 TER Table in database.

    Args:
        category: TER category
        income: Income amount

    Returns:
        float: TER rate as a decimal or None if not found
    """
    if not frappe.db.exists("DocType", "PPh 21 TER Table"):
        return None

    try:
        # First check for highest bracket that matches
        highest_bracket = frappe.get_all(
            "PPh 21 TER Table",
            filters={
                "status_pajak": category,
                "is_highest_bracket": 1,
                "income_from": ["<=", income],
            },
            fields=["rate"],
            order_by="income_from desc",
            limit=1,
        )

        if highest_bracket:
            return flt(highest_bracket[0].rate) / 100.0  # Convert percentage to decimal

        # If no highest bracket found, look for range bracket
        range_brackets = frappe.get_all(
            "PPh 21 TER Table",
            filters={
                "status_pajak": category,
                "income_from": ["<=", income],
                "income_to": [">", income],
            },
            fields=["rate"],
            order_by="income_from desc",
            limit=1,
        )

        if range_brackets:
            return flt(range_brackets[0].rate) / 100.0  # Convert percentage to decimal

        return None
    except Exception as e:
        logger.error(f"Error retrieving TER rate from database: {str(e)}")
        return None


def _get_ter_rate_from_settings(category: str, income: float) -> Optional[float]:
    """
    Get TER rate from Payroll Indonesia Settings.

    Args:
        category: TER category
        income: Income amount

    Returns:
        float: TER rate as decimal or None if not found
    """
    try:
        # Get settings
        if not frappe.db.exists("DocType", "Payroll Indonesia Settings"):
            return None

        settings = frappe.get_cached_doc("Payroll Indonesia Settings")

        # Select appropriate JSON field
        json_field = None
        if category == TER_CATEGORY_A and hasattr(settings, "ter_rate_ter_a_json"):
            json_field = settings.ter_rate_ter_a_json
        elif category == TER_CATEGORY_B and hasattr(settings, "ter_rate_ter_b_json"):
            json_field = settings.ter_rate_ter_b_json
        elif category == TER_CATEGORY_C and hasattr(settings, "ter_rate_ter_c_json"):
            json_field = settings.ter_rate_ter_c_json

        if not json_field:
            return None

        # Parse JSON and search for matching rate
        rates = json.loads(json_field)
        if not isinstance(rates, list):
            return None

        # Sort rates by income_from to ensure proper ordering
        rates = sorted(rates, key=lambda x: flt(x.get("income_from", 0)))

        for rate in rates:
            # Check highest bracket first
            if rate.get("is_highest_bracket") and income >= flt(rate.get("income_from", 0)):
                return flt(rate.get("rate", 0)) / 100.0

            # Check regular brackets
            if income >= flt(rate.get("income_from", 0)) and (
                flt(rate.get("income_to", 0)) == 0 or income < flt(rate.get("income_to", 0))
            ):
                return flt(rate.get("rate", 0)) / 100.0

        return None
    except Exception as e:
        logger.error(f"Error retrieving TER rate from settings: {str(e)}")
        return None


@functools.lru_cache(maxsize=128)
def map_ptkp_to_ter_category(ptkp_status: str) -> str:
    """
    Map PTKP status to TER category according to PMK 168/2023.

    TER has three categories:
    - TER A: For taxpayers with PTKP status TK/0
    - TER B: For taxpayers with PTKP status K/0, TK/1, TK/2
    - TER C: For taxpayers with PTKP status K/1, K/2, K/3, TK/3, etc.

    Args:
        ptkp_status: The PTKP status code (e.g., 'TK0', 'K1')

    Returns:
        str: The corresponding TER category ('TER A', 'TER B', or 'TER C')

    Raises:
        ValueError: If ptkp_status is invalid
    """
    if not ptkp_status:
        raise ValueError("PTKP status cannot be empty")

    # Normalize status_pajak by removing whitespace and converting to uppercase
    ptkp_status = ptkp_status.strip().upper()

    # First check configured mappings in the system
    try:
        # Try to get from Payroll Indonesia Settings
        if frappe.db.exists("DocType", "Payroll Indonesia Settings"):
            settings = frappe.get_cached_doc("Payroll Indonesia Settings")

            if hasattr(settings, "ptkp_ter_mapping_table") and settings.ptkp_ter_mapping_table:
                for row in settings.ptkp_ter_mapping_table:
                    if hasattr(row, "ptkp_status") and row.ptkp_status == ptkp_status:
                        # Ensure the returned category is valid
                        category = row.ter_category
                        if category in TER_CATEGORIES:
                            return category
    except Exception as e:
        logger.warning(f"Error retrieving TER mapping from settings: {str(e)}")

    # Extract prefix and suffix for mapping
    # try:
    #     prefix = ptkp_status[:2] if len(ptkp_status) >= 2 else ptkp_status
    #     suffix = ptkp_status[2:] if len(ptkp_status) >= 3 else "0"

    #     # Try to convert suffix to int if possible (for numeric comparisons)
    #     numeric_suffix = None
    #     try:
    #         numeric_suffix = int(suffix)
    #     except (ValueError, TypeError):
    #         pass
    # except Exception:
    #     raise ValueError(f"Invalid PTKP status format: {ptkp_status}")

    # Apply official mapping rules based on PMK 168/2023
    # if ptkp_status == "TK0":
    #     return TER_CATEGORY_A
    # elif prefix == "TK" and (suffix in ["1", "2"] or numeric_suffix in [1, 2]):
    #     return TER_CATEGORY_B
    # elif prefix == "TK" and (suffix == "3" or numeric_suffix == 3):
    #     return TER_CATEGORY_C
    # elif prefix == "K" and (suffix == "0" or numeric_suffix == 0):
    #     return TER_CATEGORY_B
    # elif prefix == "K" and (
    #     suffix in ["1", "2", "3"] or (numeric_suffix is not None and 1 <= numeric_suffix <= 3)
    # ):
    #     return TER_CATEGORY_C
    # elif prefix == "HB":  # Special case for HB (single parent)
    #     return TER_CATEGORY_C
    # else:
    #     raise ValueError(f"Unknown PTKP status: {ptkp_status}")

    if ptkp_status in ["TK0", "TK1", "K0"]:
        return TER_CATEGORY_A
    elif ptkp_status in ["TK2", "TK3", "K1", "K2"]:
        return TER_CATEGORY_B
    elif ptkp_status in ["K3"]:
        return TER_CATEGORY_C
    elif ptkp_status.startswith("HB"):  # Hidup Berpisah
        return TER_CATEGORY_C
    else:
        # Status tidak dikenal, default ke TER C
        frappe.log_error(f"Unknown PTKP status: {ptkp_status}", "TER Mapping")
        return TER_CATEGORY_C


def validate_ter_data_availability() -> List[str]:
    """
    Check if TER data is available in the database.

    Returns:
        List[str]: List of issues found, empty list if no issues
    """
    if not frappe.db.table_exists("PPh 21 TER Table"):
        return ["Tabel 'PPh 21 TER Table' tidak ditemukan."]

    issues = []
    for category in TER_CATEGORIES:
        try:
            # Verify entries exist for this category
            total = frappe.db.count("PPh 21 TER Table", {"status_pajak": category})
            if total == 0:
                issues.append(f"Tidak ada entri untuk kategori {category}.")
                continue

            # Verify at least one entry is marked as highest bracket
            highest = frappe.db.count(
                "PPh 21 TER Table", {"status_pajak": category, "is_highest_bracket": 1}
            )
            if highest == 0:
                issues.append(
                    f"Tidak ada bracket tertinggi (is_highest_bracket=1) untuk {category}."
                )
        except Exception as e:
            issues.append(f"Error validating {category} data: {str(e)}")

    return issues


def calculate_monthly_tax_with_ter(
    income: Union[float, int], ter_category: str
) -> Tuple[float, float]:
    """
    Calculate monthly PPh 21 using TER method.

    Args:
        income: Monthly income amount
        ter_category: TER category ('TER A', 'TER B', 'TER C')

    Returns:
        tuple: (monthly_tax, ter_rate)
    """
    # Ensure valid income
    try:
        income_value = flt(income)
        if income_value < 0:
            raise ValueError("Income cannot be negative")
    except (ValueError, TypeError):
        raise ValueError(f"Invalid income value: {income}")

    # No tax for zero income
    if income_value == 0:
        return 0.0, 0.0

    # Get normalized category
    category = normalize_ter_category(ter_category)

    # Get TER rate
    ter_rate = get_ter_rate(category, income_value)

    # Calculate tax
    monthly_tax = flt(income_value * ter_rate)

    return monthly_tax, ter_rate
