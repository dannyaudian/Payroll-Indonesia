# -*- coding: utf-8 -*-
"""setup_module.py – consolidated post‑migration setup
This file contains utilities for PPh 21 / TER setup.
It is hooked via **after_migrate** in hooks.py.
"""

from __future__ import unicode_literals

import frappe
from frappe.utils import flt

# ---------------------------------------------------------------------------
# Central utilities
# ---------------------------------------------------------------------------
from payroll_indonesia.payroll_indonesia.utils import (
    get_default_config,
    debug_log,
)

# ---------------------------------------------------------------------------
# Public hook functions
# ---------------------------------------------------------------------------


def after_sync():
    """Public hook called after app sync/migrate."""
    debug_log("Running after_sync for TER categories", "TER Setup")
    setup_ter_categories()


def after_install():
    """Hook called after app installation."""
    debug_log("Running after_install setup for TER configuration", "TER Setup")
    setup_ter_categories()


# ---------------------------------------------------------------------------
# TER setup functions
# ---------------------------------------------------------------------------


def setup_ter_categories():
    """
    Primary function to set up TER categories

    This function:
    1. Checks if TER categories already exist
    2. Gets TER rates from config
    3. Creates TER rate entries

    Returns:
        bool: True if successful, False otherwise
    """
    debug_log("Starting PPh 21 TER categories setup for PMK 168/2023", "TER Setup")

    try:
        # Check if TER categories already exist
        ter_categories_exist = check_existing_ter_categories()
        if ter_categories_exist:
            debug_log("TER categories already exist, skipping setup", "TER Setup")
            return True

        # Get TER rates from config
        ter_rates = get_ter_rates_from_config()
        if not ter_rates:
            debug_log("Failed to get TER rates from config", "TER Setup Error")
            return False

        # Create TER rates
        create_ter_rates(ter_rates)

        # Commit changes
        frappe.db.commit()
        debug_log("TER categories setup completed successfully", "TER Setup")
        return True

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error during TER categories setup: {str(e)}", "TER Setup Error")
        debug_log(f"Error during TER categories setup: {str(e)}", "TER Setup Error", trace=True)
        return False


def check_existing_ter_categories():
    """
    Check if TER categories already exist in the database

    Returns:
        bool: True if all categories exist, False otherwise
    """
    debug_log("Checking if TER categories already exist", "TER Setup")

    # Check for all three TER categories
    ter_categories = ["TER A", "TER B", "TER C"]
    for category in ter_categories:
        if not frappe.db.exists("PPh 21 TER Table", {"status_pajak": category}):
            debug_log(f"TER category {category} not found, setup required", "TER Setup")
            return False

    debug_log("All TER categories already exist", "TER Setup")
    return True


def get_ter_rates_from_config():
    """
    Get TER rates from configuration

    Returns:
        dict: Dictionary of TER rates or fallback values if config not available
    """
    debug_log("Getting TER rates from configuration", "TER Setup")

    # Try to get TER rates from config
    config = get_default_config()
    ter_rates = config.get("ter_rates", {})

    if not ter_rates:
        debug_log("TER rates not found in config, using fallback values", "TER Setup Warning")
        # Define fallback rates
        ter_rates = {
            "TER A": [
                {"income_from": 0, "income_to": 5000000, "rate": 5.0},
                {"income_from": 5000000, "income_to": 0, "rate": 15.0, "is_highest_bracket": 1},
            ],
            "TER B": [
                {"income_from": 0, "income_to": 5000000, "rate": 10.0},
                {"income_from": 5000000, "income_to": 0, "rate": 20.0, "is_highest_bracket": 1},
            ],
            "TER C": [
                {"income_from": 0, "income_to": 5000000, "rate": 15.0},
                {"income_from": 5000000, "income_to": 0, "rate": 25.0, "is_highest_bracket": 1},
            ],
        }
    else:
        # Log some statistics about the loaded TER rates
        categories_count = len(ter_rates)
        total_brackets = sum(len(rates) for rates in ter_rates.values())
        debug_log(
            f"Loaded {categories_count} TER categories with {total_brackets} rate brackets from config",
            "TER Setup",
        )

    return ter_rates


def create_ter_rates(ter_rates):
    """
    Create TER rate entries in the database

    Args:
        ter_rates (dict): Dictionary of TER rates to create
    """
    debug_log("Creating TER rate entries", "TER Setup")

    # Track statistics for logging
    created_count = 0
    skipped_count = 0
    error_count = 0

    for status, rates in ter_rates.items():
        debug_log(f"Processing rates for category {status}", "TER Setup")

        for row in rates:
            # Extract values with defaults
            income_from = flt(row.get("income_from", 0))
            income_to = flt(row.get("income_to", 0))
            rate = flt(row.get("rate", 0))

            # Check if rate already exists to maintain idempotence
            if frappe.db.exists(
                "PPh 21 TER Table",
                {
                    "status_pajak": status,
                    "income_from": income_from,
                    "income_to": income_to,
                },
            ):
                debug_log(
                    f"TER rate for {status} ({income_from:,.0f}-{income_to:,.0f}) already exists",
                    "TER Setup",
                )
                skipped_count += 1
                continue

            # Create new TER rate entry
            try:
                # Build description
                description = build_ter_description(status, row)

                # Create document
                ter_doc = frappe.new_doc("PPh 21 TER Table")
                ter_doc.update(
                    {
                        "status_pajak": status,
                        "income_from": income_from,
                        "income_to": income_to,
                        "rate": rate,
                        "is_highest_bracket": row.get("is_highest_bracket", 0),
                        "description": description,
                    }
                )

                # Insert with ignore_permissions
                ter_doc.flags.ignore_permissions = True
                ter_doc.insert(ignore_permissions=True)

                created_count += 1
                debug_log(
                    f"Created TER rate for {status}: {income_from:,.0f}-{income_to:,.0f} at {rate}%",
                    "TER Setup",
                )

            except Exception as e:
                error_count += 1
                debug_log(
                    f"Error creating TER rate for {status} ({income_from:,.0f}-{income_to:,.0f}): {str(e)}",
                    "TER Setup Error",
                )
                frappe.log_error(
                    f"Error creating TER rate for {status}: {str(e)}\n\nData: {row}",
                    "TER Setup Error",
                )

    # Log summary
    debug_log(
        f"TER rate creation summary: created={created_count}, skipped={skipped_count}, errors={error_count}",
        "TER Setup",
    )


def build_ter_description(status, row):
    """
    Build a descriptive label for TER rate entries

    Args:
        status (str): TER category (A, B, or C)
        row (dict): Rate data

    Returns:
        str: Formatted description string
    """
    inc_from = flt(row.get("income_from", 0))
    inc_to = flt(row.get("income_to", 0))

    # Different formatting for highest bracket
    if row.get("is_highest_bracket") or inc_to == 0:
        return f"{status} > {inc_from:,.0f}"

    # Standard formatting for regular brackets
    return f"{status} {inc_from:,.0f} – {inc_to:,.0f}"
