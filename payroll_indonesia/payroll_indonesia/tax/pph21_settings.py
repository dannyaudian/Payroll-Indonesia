# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 17:10:22 by dannyaudian

import frappe
from frappe import _

# from payroll_indonesia.payroll_indonesia.utils import get_ptkp_settings

# Import centralized cache utilities
from payroll_indonesia.utilities.cache_utils import clear_tax_settings_cache


def on_update(doc, method):
    """Handler untuk event on_update pada PPh 21 Settings"""
    try:
        # Clear tax settings cache whenever settings are updated
        clear_tax_settings_cache()

        # Validate settings
        validate_brackets(doc)
        validate_ptkp_entries(doc)

        # Perform strict TER table validation if TER method is selected
        if doc.calculation_method == "TER":
            validate_ter_table(strict=True)

    except Exception as e:
        # Handle ValidationError separately - those should be shown to the user
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # For other errors, log and re-raise with a clearer message
        frappe.log_error(
            "Error updating PPh 21 Settings: {0}".format(str(e)), "PPh 21 Settings Update Error"
        )
        frappe.throw(
            _("Error updating PPh 21 Settings: {0}").format(str(e)),
            title=_("Settings Update Failed"),
        )


def validate_brackets(doc):
    """Ensure tax brackets are continuous and non-overlapping"""
    try:
        if not doc.bracket_table:
            # Non-critical warning - continue processing
            frappe.msgprint(_("At least one tax bracket should be defined"), indicator="orange")
            return

        # Sort by income_from
        sorted_brackets = sorted(doc.bracket_table, key=lambda x: x.income_from)

        # Check for gaps or overlaps
        for i in range(len(sorted_brackets) - 1):
            current = sorted_brackets[i]
            next_bracket = sorted_brackets[i + 1]

            if current.income_to != next_bracket.income_from:
                # Non-critical warning - continue processing
                frappe.msgprint(
                    _(
                        "Warning: Tax brackets should be continuous. Gap found between {0} and {1}"
                    ).format(current.income_to, next_bracket.income_from),
                    indicator="orange",
                )

    except Exception as e:
        # Non-critical error - log and continue
        frappe.log_error(
            "Error validating tax brackets: {0}".format(str(e)), "Bracket Validation Error"
        )
        frappe.msgprint(
            _("Error validating tax brackets. Please check your bracket configuration."),
            indicator="orange",
        )


def validate_ptkp_entries(doc):
    """Validate PTKP entries against required values"""
    try:
        required_status = ["TK0", "K0", "K1", "K2", "K3"]

        if not doc.ptkp_table:
            # Critical validation failure - throw error
            frappe.throw(
                _("PTKP values must be defined for tax calculation"), title=_("Missing PTKP Values")
            )
            return

        defined_status = [p.status_pajak for p in doc.ptkp_table]

        missing_status = []
        for status in required_status:
            if status not in defined_status:
                missing_status.append(status)

        if missing_status:
            # Non-critical warning - continue processing
            frappe.msgprint(
                _("Warning: Missing PTKP definition for status: {0}").format(
                    ", ".join(missing_status)
                ),
                indicator="orange",
            )

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # For other errors, log and continue
        frappe.log_error(
            "Error validating PTKP entries: {0}".format(str(e)), "PTKP Validation Error"
        )
        frappe.msgprint(
            _("Error validating PTKP entries. Please check your PTKP configuration."),
            indicator="orange",
        )


def validate_ter_table(strict=False):
    """
    Validate TER table if TER method is selected

    Args:
        strict (bool): If True, throws an error when TER table is empty
                       If False, only shows a warning message
    """
    try:
        count = frappe.db.count("PPh 21 TER Table")

        if count == 0:
            message = _(
                "Tarif Efektif Rata-rata (TER) table is empty. TER table is required for TER calculation method."
            )

            if strict:
                # Enforce strict validation - throw error
                frappe.throw(
                    message
                    + " "
                    + _("Please add entries to the TER table before using this method."),
                    title=_("TER Table Required"),
                )
            else:
                # Show warning only
                frappe.msgprint(
                    message
                    + " "
                    + _("Please fill in the TER table for accurate tax calculations."),
                    indicator="orange",
                )
        elif count < 3:
            # Even with some entries, warn if there are too few
            frappe.msgprint(
                _(
                    "TER table has very few entries ({0}). For proper TER calculation, "
                    "ensure all income brackets and TER categories are covered."
                ).format(count),
                indicator="orange",
            )

    except Exception as e:
        # Handle ValidationError separately
        if isinstance(e, frappe.exceptions.ValidationError):
            raise

        # For non-critical errors when strict=False, log and continue
        if not strict:
            frappe.log_error(
                "Error validating TER table: {0}".format(str(e)), "TER Table Validation Error"
            )
            frappe.msgprint(
                _(
                    "Error validating TER table configuration. TER calculations may not work correctly."
                ),
                indicator="orange",
            )
        else:
            # For strict mode, log and re-throw
            frappe.log_error(
                "Error validating TER table (strict mode): {0}".format(str(e)),
                "TER Table Validation Error",
            )
            frappe.throw(
                _("Error validating TER table: {0}").format(str(e)),
                title=_("TER Validation Failed"),
            )


@frappe.whitelist()
def check_ter_configuration():
    """
    Check if TER configuration is complete and valid

    Returns:
        dict: Status of TER configuration check
    """
    try:
        # Get current PPh 21 settings
        pph_settings = frappe.get_single("PPh 21 Settings")

        # Get TER table count
        ter_table_count = frappe.db.count("PPh 21 TER Table")

        # Check if TER is enabled in settings
        ter_enabled = (
            hasattr(pph_settings, "calculation_method")
            and pph_settings.calculation_method == "TER"
            and hasattr(pph_settings, "use_ter")
            and pph_settings.use_ter
        )

        # Get TER table categories - check if we have required categories
        ter_categories = []
        if ter_table_count > 0:
            categories = frappe.db.sql(
                "SELECT DISTINCT status_pajak FROM `tabPPh 21 TER Table` ORDER BY status_pajak",
                as_dict=False,
            )
            ter_categories = [c[0] for c in categories]

        required_categories = ["TER A", "TER B", "TER C"]
        missing_categories = [c for c in required_categories if c not in ter_categories]

        # Return configuration status
        return {
            "ter_enabled": ter_enabled,
            "ter_table_count": ter_table_count,
            "ter_table_empty": ter_table_count == 0,
            "ter_categories": ter_categories,
            "missing_categories": missing_categories,
            "status": "ok" if ter_table_count > 0 and not missing_categories else "warning",
            "message": (
                _("TER configuration is complete")
                if ter_table_count > 0 and not missing_categories
                else _("TER configuration is incomplete")
            ),
        }

    except Exception as e:
        # Non-critical error in check function - log and return error status
        frappe.log_error(
            "Error checking TER configuration: {0}".format(str(e)), "TER Configuration Check Error"
        )
        return {
            "status": "error",
            "message": _("Error checking TER configuration: {0}").format(str(e)),
        }


def setup_default_ter_table():
    """
    Create default TER table entries based on PMK 168/2023
    This function can be called during system setup or when missing TER entries

    Returns:
        int: Number of entries created
    """
    try:
        # Check if TER table is already populated
        existing_count = frappe.db.count("PPh 21 TER Table")
        if existing_count > 0:
            # Non-critical info - log and return
            frappe.msgprint(
                _("TER table already has {0} entries. Default setup skipped.").format(
                    existing_count
                ),
                indicator="blue",
            )
            return 0

        # Default TER rates based on PMK 168/2023
        default_ter_rates = [
            # TER A (TK/0)
            {
                "status_pajak": "TER A",
                "income_from": 0,
                "income_to": 500000,
                "rate": 0,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER A",
                "income_from": 500000,
                "income_to": 1000000,
                "rate": 1,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER A",
                "income_from": 1000000,
                "income_to": 2000000,
                "rate": 2,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER A",
                "income_from": 2000000,
                "income_to": 5000000,
                "rate": 5,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER A",
                "income_from": 5000000,
                "income_to": 10000000,
                "rate": 8,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER A",
                "income_from": 10000000,
                "income_to": 20000000,
                "rate": 12,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER A",
                "income_from": 20000000,
                "income_to": 0,
                "rate": 34,
                "is_highest_bracket": 1,
            },
            # TER B (K/0, TK/1, TK/2, K/1)
            {
                "status_pajak": "TER B",
                "income_from": 0,
                "income_to": 1000000,
                "rate": 0,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER B",
                "income_from": 1000000,
                "income_to": 2000000,
                "rate": 1,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER B",
                "income_from": 2000000,
                "income_to": 5000000,
                "rate": 2,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER B",
                "income_from": 5000000,
                "income_to": 10000000,
                "rate": 5,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER B",
                "income_from": 10000000,
                "income_to": 20000000,
                "rate": 10,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER B",
                "income_from": 20000000,
                "income_to": 0,
                "rate": 30,
                "is_highest_bracket": 1,
            },
            # TER C (All other PTKP statuses)
            {
                "status_pajak": "TER C",
                "income_from": 0,
                "income_to": 2000000,
                "rate": 0,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER C",
                "income_from": 2000000,
                "income_to": 5000000,
                "rate": 1,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER C",
                "income_from": 5000000,
                "income_to": 10000000,
                "rate": 3,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER C",
                "income_from": 10000000,
                "income_to": 20000000,
                "rate": 7,
                "is_highest_bracket": 0,
            },
            {
                "status_pajak": "TER C",
                "income_from": 20000000,
                "income_to": 0,
                "rate": 25,
                "is_highest_bracket": 1,
            },
        ]

        # Create TER table entries
        created_entries = 0

        for rate_data in default_ter_rates:
            try:
                description = ""

                # Generate sensible description
                if rate_data["is_highest_bracket"]:
                    description = "{0} > {1:,.0f}".format(
                        rate_data["status_pajak"], rate_data["income_from"]
                    )
                else:
                    description = "{0} {1:,.0f} - {2:,.0f}".format(
                        rate_data["status_pajak"], rate_data["income_from"], rate_data["income_to"]
                    )

                ter_entry = frappe.get_doc(
                    {
                        "doctype": "PPh 21 TER Table",
                        "status_pajak": rate_data["status_pajak"],
                        "income_from": rate_data["income_from"],
                        "income_to": rate_data["income_to"],
                        "rate": rate_data["rate"],
                        "is_highest_bracket": rate_data["is_highest_bracket"],
                        "description": description,
                    }
                )

                # Link to parent document if appropriate
                if frappe.db.exists("DocType", "PPh 21 Settings"):
                    doc_list = frappe.db.get_all("PPh 21 Settings")
                    if doc_list:
                        ter_entry.parent = "PPh 21 Settings"
                        ter_entry.parentfield = "ter_rates"
                        ter_entry.parenttype = "PPh 21 Settings"

                # Insert with permission bypass
                ter_entry.flags.ignore_permissions = True
                ter_entry.insert(ignore_permissions=True)
                created_entries += 1

            except Exception as entry_error:
                # Non-critical error for individual entry - log and continue with others
                frappe.log_error(
                    "Error creating TER table entry for {0}: {1}".format(
                        rate_data["status_pajak"], str(entry_error)
                    ),
                    "TER Entry Creation Error",
                )
                continue

        frappe.db.commit()

        if created_entries > 0:
            frappe.msgprint(
                _(
                    "Default TER table has been set up with {0} entries based on PMK 168/2023"
                ).format(created_entries),
                indicator="green",
            )
        else:
            frappe.msgprint(
                _("No TER entries were created. Please check the error log."), indicator="red"
            )

        return created_entries

    except Exception as e:
        # Critical error in setup - rollback and throw
        frappe.log_error(
            "Error setting up default TER table: {0}".format(str(e)), "TER Setup Error"
        )
        frappe.db.rollback()
        frappe.throw(
            _("Error setting up default TER table: {0}").format(str(e)), title=_("TER Setup Failed")
        )
        return 0
