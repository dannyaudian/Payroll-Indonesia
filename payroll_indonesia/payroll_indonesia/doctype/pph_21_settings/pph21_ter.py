# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 13:12:56 by dannyaudian

import frappe
from frappe import _
from payroll_indonesia.payroll_indonesia.utils import get_settings, get_ter_category


def get_ter_rate(employee_doc, monthly_income):
    """
    Get TER (Tarif Efektif Rata-rata) rate for employee based on PMK 168/2023

    Args:
        employee_doc (Employee): Employee document or dict with status_pajak field
        monthly_income (float): Monthly gross income amount

    Returns:
        float: TER rate (as decimal, e.g. 0.05 for 5%)
    """
    if not employee_doc:
        frappe.throw(_("Employee document is required to calculate TER rate"))

    status_pajak = employee_doc.get("status_pajak")
    if not status_pajak:
        frappe.throw(_("Employee tax status (Status Pajak) is not set"))

    # Map PTKP status to TER category according to PMK 168/2023 using centralized settings
    ter_category = map_ptkp_to_ter_category(status_pajak)

    # Query the TER table for matching bracket
    ter = frappe.db.sql(
        """
        SELECT rate
        FROM `tabPPh 21 TER Table`
        WHERE status_pajak = %s
          AND %s >= income_from
          AND (%s < income_to OR income_to = 0)
        LIMIT 1
    """,
        (ter_category, monthly_income, monthly_income),
        as_dict=1,
    )

    # If no TER rate found in table, try to get from Payroll Indonesia Settings
    if not ter:
        try:
            # Get centralized settings
            settings = get_settings()
            rate = settings.get_ter_rate(ter_category, monthly_income)
            if rate:
                # Convert to decimal since get_ter_rate returns percentage
                return float(rate) / 100.0
        except Exception as e:
            frappe.log_error(f"Error getting TER rate from settings: {str(e)}", "TER Rate Error")

        # If still not found, throw error
        frappe.throw(
            _(
                "No TER rate found for category {0} (mapped from status {1}) and income {2}. "
                "Please check PPh 21 TER Table settings."
            ).format(
                ter_category, status_pajak, frappe.format(monthly_income, {"fieldtype": "Currency"})
            )
        )

    # Convert percent to decimal (e.g., 5% to 0.05)
    return float(ter[0].rate) / 100.0


def map_ptkp_to_ter_category(status_pajak):
    """
    Map PTKP status to TER category based on PMK 168/2023

    Args:
        status_pajak (str): PTKP status (e.g., 'TK0', 'K1', etc.)

    Returns:
        str: TER category ('TER A', 'TER B', or 'TER C')
    """
    # Use centralized mapping from Payroll Indonesia Settings
    try:
        # Get TER category from centralized settings
        ter_category = get_ter_category(status_pajak)
        if ter_category:
            return ter_category
    except Exception as e:
        frappe.log_error(f"Error getting TER category from settings: {str(e)}", "TER Mapping Error")

    # Fallback mapping as per PMK 168/2023 if settings are not available
    mapping = {
        # TER A: PTKP TK/0 (Rp 54 juta/tahun)
        "TK0": "TER A",
        # TER TK1 : TER A
        "TK1": "TER A",
        # TER B: PTKP K/0 dan TK/1 (Rp 58,5 juta/tahun)
        "K0": "TER B",
        # "TK1": "TER B",
        # TER C: PTKP K/1, TK/2, K/2, TK/3, K/3, dst (Rp 63 juta+/tahun)
        "K1": "TER C",
        "TK2": "TER C",
        "K2": "TER C",
        "TK3": "TER C",
        "K3": "TER C",
        "HB0": "TER C",
        "HB1": "TER C",
        "HB2": "TER C",
        "HB3": "TER C",
    }

    # Return mapped category or default to TER C for unknown statuses
    return mapping.get(status_pajak, "TER C")


def calculate_pph21_with_ter(employee, monthly_income):
    """
    Calculate PPh 21 amount using TER method based on PMK 168/2023

    Args:
        employee (string or dict): Employee ID or document
        monthly_income (float): Monthly gross income amount

    Returns:
        float: PPh 21 amount to be deducted
    """
    # Ensure we have employee document
    if isinstance(employee, str):
        employee_doc = frappe.get_doc("Employee", employee)
    else:
        employee_doc = employee

    # Get TER rate for this employee and income
    ter_rate = get_ter_rate(employee_doc, monthly_income)

    # Simply multiply income by TER rate
    pph21_amount = monthly_income * ter_rate

    return pph21_amount


def setup_default_ter_rates():
    """
    Setup default TER rates based on PMK 168/2023

    Uses the Payroll Indonesia Settings for TER rates if available, or falls back to defaults
    """
    # Check if we already have TER rates
    existing_count = frappe.db.count("PPh 21 TER Table")
    if existing_count > 10:  # Arbitrary threshold
        frappe.msgprint(
            _("TER rates are already set up ({0} entries found)").format(existing_count)
        )
        return

    # Try to get TER rates from Payroll Indonesia Settings
    settings = get_settings()

    ter_rates = {}
    try:
        if hasattr(settings, "ter_rates") and settings.ter_rates:
            if isinstance(settings.ter_rates, str):
                ter_rates = frappe.parse_json(settings.ter_rates)
            else:
                ter_rates = settings.ter_rates
    except Exception as e:
        frappe.log_error(f"Error parsing TER rates from settings: {str(e)}", "TER Setup Error")

    # Use the central settings if available
    if ter_rates:
        for category, rates in ter_rates.items():
            for rate_data in rates:
                # Skip if already exists
                if frappe.db.exists(
                    "PPh 21 TER Table",
                    {
                        "status_pajak": category,
                        "income_from": rate_data.get("income_from", 0),
                        "income_to": rate_data.get("income_to", 0),
                    },
                ):
                    continue

                # Create sensible description
                description = ""
                if rate_data.get("is_highest_bracket", 0) or rate_data.get("income_to", 0) == 0:
                    description = f"{category} > {float(rate_data.get('income_from', 0)):,.0f}"
                else:
                    description = f"{category} {float(rate_data.get('income_from', 0)):,.0f} - {float(rate_data.get('income_to', 0)):,.0f}"

                # Create TER entry
                doc = frappe.new_doc("PPh 21 TER Table")
                doc.status_pajak = category
                doc.income_from = float(rate_data.get("income_from", 0))
                doc.income_to = float(rate_data.get("income_to", 0))
                doc.rate = float(rate_data.get("rate", 0))
                doc.is_highest_bracket = rate_data.get("is_highest_bracket", 0)
                doc.description = description
                doc.insert()

        frappe.db.commit()
        frappe.msgprint(_("TER rates set up from Payroll Indonesia Settings"))
        return

    # Fallback to hardcoded TER rates based on PMK 168/2023
    default_rates = [
        # TER A (PTKP TK/0: Rp 54 juta/tahun)
        {"status_pajak": "TER A", "income_from": 0, "income_to": 4500000, "rate": 0.0},
        {"status_pajak": "TER A", "income_from": 4500000, "income_to": 8000000, "rate": 2.5},
        {"status_pajak": "TER A", "income_from": 8000000, "income_to": 13000000, "rate": 5.0},
        {"status_pajak": "TER A", "income_from": 13000000, "income_to": 21000000, "rate": 7.5},
        {"status_pajak": "TER A", "income_from": 21000000, "income_to": 32000000, "rate": 10.0},
        {
            "status_pajak": "TER A",
            "income_from": 32000000,
            "income_to": 0,
            "rate": 12.5,
            "is_highest_bracket": 1,
        },
        # TER B (PTKP K/0, TK/1: Rp 58,5 juta/tahun)
        {"status_pajak": "TER B", "income_from": 0, "income_to": 4900000, "rate": 0.0},
        {"status_pajak": "TER B", "income_from": 4900000, "income_to": 8500000, "rate": 2.0},
        {"status_pajak": "TER B", "income_from": 8500000, "income_to": 13500000, "rate": 4.5},
        {"status_pajak": "TER B", "income_from": 13500000, "income_to": 22000000, "rate": 7.0},
        {"status_pajak": "TER B", "income_from": 22000000, "income_to": 33000000, "rate": 9.5},
        {
            "status_pajak": "TER B",
            "income_from": 33000000,
            "income_to": 0,
            "rate": 12.0,
            "is_highest_bracket": 1,
        },
        # TER C (PTKP K/1, TK/2, K/2, TK/3, K/3, dll: Rp 63 juta+/tahun)
        {"status_pajak": "TER C", "income_from": 0, "income_to": 5300000, "rate": 0.0},
        {"status_pajak": "TER C", "income_from": 5300000, "income_to": 9000000, "rate": 1.5},
        {"status_pajak": "TER C", "income_from": 9000000, "income_to": 14000000, "rate": 4.0},
        {"status_pajak": "TER C", "income_from": 14000000, "income_to": 23000000, "rate": 6.5},
        {"status_pajak": "TER C", "income_from": 23000000, "income_to": 34000000, "rate": 9.0},
        {
            "status_pajak": "TER C",
            "income_from": 34000000,
            "income_to": 0,
            "rate": 11.5,
            "is_highest_bracket": 1,
        },
    ]

    # Create TER rate records if they don't exist
    for rate_data in default_rates:
        if not frappe.db.exists(
            "PPh 21 TER Table",
            {
                "status_pajak": rate_data["status_pajak"],
                "income_from": rate_data["income_from"],
                "income_to": rate_data["income_to"],
            },
        ):
            doc = frappe.new_doc("PPh 21 TER Table")
            doc.update(rate_data)
            doc.insert()

    # Update Payroll Indonesia Settings with the default TER rates
    try:
        # Group rates by category
        ter_by_category = {}
        for rate in default_rates:
            category = rate["status_pajak"]
            if category not in ter_by_category:
                ter_by_category[category] = []

            rate_obj = {
                "income_from": rate["income_from"],
                "income_to": rate["income_to"],
                "rate": rate["rate"],
            }

            if "is_highest_bracket" in rate and rate["is_highest_bracket"]:
                rate_obj["is_highest_bracket"] = 1

            ter_by_category[category].append(rate_obj)

        # Update settings
        if ter_by_category:
            settings.ter_rates = frappe.as_json(ter_by_category)
            settings.flags.ignore_validate = True
            settings.flags.ignore_permissions = True
            settings.save(ignore_permissions=True)
    except Exception as e:
        frappe.log_error(
            f"Error updating TER rates in Payroll Indonesia Settings: {str(e)}", "TER Setup Error"
        )

    frappe.db.commit()
    frappe.msgprint(_("Default TER rates set up based on PMK 168/2023"))
