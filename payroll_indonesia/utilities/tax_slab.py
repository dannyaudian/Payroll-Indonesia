# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 09:20:06 by dannyaudian

"""
Tax Slab utilities for Indonesian income tax.

This module provides functions to set up and manage income tax slabs
for Indonesian progressive tax calculations.
"""

from typing import Any, Dict, Optional, Union, List

import frappe
from frappe import _
from frappe.utils import getdate

from payroll_indonesia.frappe_helpers import logger

__all__ = ["setup_income_tax_slab"]


def setup_income_tax_slab(defaults: Optional[Dict[str, Any]] = None, *args, **kwargs) -> bool:
    """
    Create Income Tax Slab for Indonesia if it doesn't exist.
    
    Args:
        defaults: Configuration data from defaults.json (optional)
        
    Returns:
        bool: True if created or already exists, False if failed
    """
    try:
        # Check if table exists
        if not frappe.db.table_exists("Income Tax Slab"):
            logger.warning("Income Tax Slab table does not exist")
            return False
            
        # Check if already exists - safely handle column existence
        has_is_default = frappe.db.has_column('Income Tax Slab', 'is_default')
        
        # Prepare filters based on available columns
        filters = {"name": "Indonesia Income Tax"}
        if has_is_default:
            filters = [
                ["name", "=", "Indonesia Income Tax"],
                ["or", [["currency", "=", "IDR"], ["is_default", "=", 1]]]
            ]
            
        # Check if tax slab already exists
        if frappe.db.exists("Income Tax Slab", filters):
            logger.info("Income Tax Slab for Indonesia already exists")
            return True
            
        # Load defaults if not provided
        if defaults is None:
            from payroll_indonesia.setup.settings_migration import _load_defaults
            defaults = _load_defaults()
            
        # Get company
        company = frappe.db.get_default("company")
        if not company and frappe.db.table_exists("Company"):
            companies = frappe.get_all("Company", pluck="name")
            company = companies[0] if companies else None
            
        if not company:
            logger.warning("No company found for income tax slab")
            return False
            
        # Get tax brackets from config
        tax_brackets = defaults.get("tax_brackets", [])
        if not tax_brackets:
            # Use default brackets if not in config
            tax_brackets = [
                {"income_from": 0, "income_to": 60000000, "tax_rate": 5},
                {"income_from": 60000000, "income_to": 250000000, "tax_rate": 15},
                {"income_from": 250000000, "income_to": 500000000, "tax_rate": 25},
                {"income_from": 500000000, "income_to": 5000000000, "tax_rate": 30},
                {"income_from": 5000000000, "income_to": 0, "tax_rate": 35},
            ]
            
        # Create tax slab
        tax_slab = frappe.new_doc("Income Tax Slab")
        tax_slab.title = "Indonesia Income Tax"
        tax_slab.name = "Indonesia Income Tax"
        tax_slab.effective_from = getdate("2023-01-01")
        tax_slab.company = company
        tax_slab.currency = defaults.get("defaults", {}).get("currency", "IDR")
        
        # Set is_default if the column exists
        if has_is_default:
            tax_slab.is_default = 1
            tax_slab.disabled = 0
            
        # Add tax brackets
        for bracket in tax_brackets:
            tax_slab.append(
                "slabs",
                {
                    "from_amount": float(bracket.get("income_from", 0)),
                    "to_amount": float(bracket.get("income_to", 0)),
                    "percent_deduction": float(bracket.get("tax_rate", 0)),
                },
            )
            
        # Save with flags to bypass validation
        tax_slab.flags.ignore_permissions = True
        tax_slab.flags.ignore_mandatory = True
        tax_slab.insert()
        
        logger.info(f"Successfully created Income Tax Slab: {tax_slab.name}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating Income Tax Slab: {str(e)}")
        
        # Try to find existing tax slab as fallback
        try:
            existing_slabs = frappe.get_all("Income Tax Slab", limit=1)
            if existing_slabs:
                logger.info(f"Found existing tax slab as fallback: {existing_slabs[0].name}")
                return True
        except Exception:
            pass
            
        return False