# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from typing import Dict, Any, Optional, List, Union
import frappe
from frappe import _
from frappe.utils import flt, cint

from payroll_indonesia.frappe_helpers import logger

__all__ = ["setup_income_tax_slab", "get_default_tax_slab"]


def setup_income_tax_slab(defaults: Optional[Dict[str, Any]] = None) -> bool:
    """
    Setup Indonesia Income Tax Slab based on defaults.

    Args:
        defaults: Dictionary of default values, typically from frappe.defaults.get_defaults()

    Returns:
        bool: True if the tax slab was created, False if it already exists
    """
    try:
        logger.info("Setting up Income Tax Slab for Indonesia")

        # Check if Income Tax Slab doctype exists
        if not frappe.db.exists("DocType", "Income Tax Slab"):
            logger.warning("Income Tax Slab DocType does not exist, skipping setup")
            return False

        # Define default parameters
        currency = "IDR"
        name = f"Indonesia Tax Slab - {currency}"

        # Check if the tax slab already exists
        if frappe.db.exists("Income Tax Slab", name):
            logger.info(f"Income Tax Slab '{name}' already exists, skipping")
            return False

        # Get tax brackets from defaults or use standard brackets
        if defaults and "tax_brackets" in defaults:
            tax_brackets = defaults.get("tax_brackets", [])
        else:
            # Standard Indonesian tax brackets
            tax_brackets = [
                {"from_amount": 0, "to_amount": 60000000, "percent_deduction": 5},
                {"from_amount": 60000000, "to_amount": 250000000, "percent_deduction": 15},
                {"from_amount": 250000000, "to_amount": 500000000, "percent_deduction": 25},
                {"from_amount": 500000000, "to_amount": 5000000000, "percent_deduction": 30},
                {"from_amount": 5000000000, "to_amount": 0, "percent_deduction": 35},
            ]

        # Create new Income Tax Slab
        tax_slab = frappe.new_doc("Income Tax Slab")
        tax_slab.name = name
        tax_slab.currency = currency
        tax_slab.effective_from = "2023-01-01"
        tax_slab.company = frappe.defaults.get_global_default("company")
        tax_slab.description = "Standard Indonesia Income Tax Slab"

        # Add is_default if the column exists
        if frappe.db.has_column("Income Tax Slab", "is_default"):
            tax_slab.is_default = 1

        # Add tax brackets
        for bracket in tax_brackets:
            tax_slab.append(
                "slabs",
                {
                    "from_amount": flt(bracket.get("from_amount", 0)),
                    "to_amount": flt(bracket.get("to_amount", 0)),
                    "percent_deduction": flt(bracket.get("percent_deduction", 0)),
                    "condition": bracket.get("condition", ""),
                },
            )

        # Save the document
        tax_slab.flags.ignore_permissions = True
        tax_slab.insert()
        frappe.db.commit()

        logger.info(f"Successfully created Income Tax Slab '{name}'")
        return True

    except Exception as e:
        logger.error(f"Error setting up Income Tax Slab: {str(e)}")
        return False


def get_default_tax_slab(create_if_missing: bool = True) -> Optional[str]:
    """
    Get default Income Tax Slab for Indonesia (IDR). Create if missing.

    Args:
        create_if_missing: Whether to create the default tax slab if it doesn't exist

    Returns:
        str: Name of the default slab, or None if not found/created
    """
    try:
        slab_doctype = "Income Tax Slab"
        currency = "IDR"

        # Check if the DocType exists
        if not frappe.db.exists("DocType", slab_doctype):
            logger.warning(f"DocType '{slab_doctype}' does not exist")
            return None

        # Check if is_default column exists
        has_is_default = frappe.db.has_column(slab_doctype, "is_default")

        # Try to find the default slab
        if has_is_default:
            default_slab = frappe.db.get_value(
                slab_doctype, {"currency": currency, "is_default": 1}, "name"
            )
        else:
            logger.warning(
                "'is_default' column missing in Income Tax Slab. Skipping 'is_default=1' filter."
            )
            default_slab = frappe.db.get_value(slab_doctype, {"currency": currency}, "name")

        # Return if found
        if default_slab:
            return default_slab

        # Create if missing and requested
        if create_if_missing:
            logger.info("Default tax slab not found, attempting to create")
            setup_income_tax_slab()

            # Try to find again
            if has_is_default:
                default_slab = frappe.db.get_value(
                    slab_doctype, {"currency": currency, "is_default": 1}, "name"
                )
            else:
                default_slab = frappe.db.get_value(slab_doctype, {"currency": currency}, "name")

            return default_slab

        return None

    except Exception as e:
        logger.error(f"Error retrieving default tax slab: {str(e)}")
        return None


def get_income_tax_for_salary(annual_income: float, tax_slab: Optional[str] = None) -> float:
    """
    Calculate income tax for a given annual income using a specified tax slab.

    Args:
        annual_income: Annual taxable income
        tax_slab: Name of the tax slab to use (if None, uses default)

    Returns:
        float: Calculated annual income tax
    """
    try:
        if not tax_slab:
            tax_slab = get_default_tax_slab()
            if not tax_slab:
                logger.error("No tax slab found and could not create default")
                return 0.0

        # Get the tax slab document
        slab_doc = frappe.get_doc("Income Tax Slab", tax_slab)
        if not slab_doc or not hasattr(slab_doc, "slabs"):
            logger.error(f"Invalid tax slab document: {tax_slab}")
            return 0.0

        # Calculate tax
        total_tax = 0.0
        remaining_income = annual_income

        # Sort slabs by from_amount
        sorted_slabs = sorted(slab_doc.slabs, key=lambda x: flt(x.from_amount))

        for slab in sorted_slabs:
            # Skip if no more income to tax
            if remaining_income <= 0:
                break

            # Check if this is the highest bracket (to_amount = 0)
            is_highest_bracket = flt(slab.to_amount) == 0

            # Calculate taxable amount in this bracket
            if is_highest_bracket:
                taxable_amount = remaining_income
            else:
                taxable_amount = min(remaining_income, flt(slab.to_amount) - flt(slab.from_amount))

            # Calculate tax for this bracket
            tax_for_bracket = taxable_amount * flt(slab.percent_deduction) / 100
            total_tax += tax_for_bracket

            # Reduce remaining income
            remaining_income -= taxable_amount

        return flt(total_tax, 2)

    except Exception as e:
        logger.error(f"Error calculating income tax: {str(e)}")
        return 0.0
