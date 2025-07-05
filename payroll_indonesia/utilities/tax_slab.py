# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-05 by dannyaudian

"""
tax_slab.py – Utilities for Income Tax Slab setup and management in Payroll Indonesia.
Provides idempotent setup suitable for running during after_migrate.
"""

from typing import Optional
import frappe
from frappe.utils import getdate
from frappe.exceptions import DoesNotExistError
from payroll_indonesia.frappe_helpers import logger

__all__ = [
    "setup_income_tax_slab",
    "create_income_tax_slab",
    "get_default_tax_slab",
    "update_salary_structures",
    "update_existing_assignments",
]


def setup_income_tax_slab() -> bool:
    """
    Ensure a default Income Tax Slab for IDR exists.
    Idempotent, safe to call during after_migrate.
    Creates a stub slab if no Company exists.
    Returns True if slab exists or created, False on error.
    """
    slab_doctype = "Income Tax Slab"
    stub_slab_name = "Default Income Tax Slab"
    currency = "IDR"

    if not frappe.db.table_exists(slab_doctype):
        logger.warning("Income Tax Slab DocType does not exist. Skipping slab setup.")
        return False

    # Check if a default slab for IDR exists
    default_slab = frappe.db.get_value(
        slab_doctype, {"currency": currency, "is_default": 1}, "name"
    )
    if default_slab:
        logger.info(f"Income Tax Slab already exists: '{default_slab}'")
        return True

    # If not, check if any IDR slab exists
    any_slab = frappe.db.get_value(slab_doctype, {"currency": currency}, "name")
    if any_slab:
        logger.info(f"At least one IDR Income Tax Slab exists: '{any_slab}'")
        return True

    # Attempt to find a company, fallback to stub if missing
    company = _find_any_company_name()
    if not company:
        logger.warning(
            "No Company found; creating minimal stub Income Tax Slab with company unset."
        )

    try:
        slab = frappe.new_doc(slab_doctype)
        slab.slab_name = stub_slab_name
        slab.company = company or ""
        slab.is_default = 1
        slab.enabled = 1
        slab.income_tax_slab_type = "Regular"
        slab.currency = currency
        slab.effective_from = getdate("2023-01-01")
        slab.flags.ignore_permissions = True
        slab.flags.ignore_mandatory = True

        # Add minimal slab row
        slab.append(
            "slabs",
            {
                "from_amount": 0,
                "to_amount": 0,
                "rate": 0,
                "fixed_amount": 0,
            },
        )

        slab.insert(ignore_permissions=True, ignore_mandatory=True)
        frappe.db.commit()
        logger.info(
            "Created minimal stub Income Tax Slab: '%s' (company: %s)",
            stub_slab_name,
            company or "<none>",
        )
        return True
    except Exception as e:
        frappe.db.rollback()
        logger.error(f"Error creating default Income Tax Slab: {str(e)}")
        frappe.log_error(
            f"Error creating default Income Tax Slab: {str(e)}\n{frappe.get_traceback()}",
            "Income Tax Slab Setup Error",
        )
        return False


def create_income_tax_slab() -> Optional[str]:
    """
    Create Indonesia Income Tax Slab if not already exists.
    Idempotent: will not create duplicate if already present.
    Returns the slab name if created or already exists, None if fails.
    """
    slab_doctype = "Income Tax Slab"
    slab_name = "Indonesia Income Tax"
    currency = "IDR"
    company = _find_any_company_name()
    if not frappe.db.table_exists(slab_doctype):
        logger.warning("Income Tax Slab DocType does not exist. Skipping creation.")
        return None

    # Check for existing slab by name
    if frappe.db.exists(slab_doctype, {"slab_name": slab_name}):
        existing = frappe.db.get_value(slab_doctype, {"slab_name": slab_name}, "name")
        logger.info(f"Income Tax Slab '{slab_name}' already exists: '{existing}'")
        return existing

    # Check for existing default slab with same attributes
    existing_slabs = frappe.get_all(
        slab_doctype,
        filters={"currency": currency, "is_default": 1},
        fields=["name"],
        limit=1,
    )
    if existing_slabs:
        logger.info(
            f"Default Income Tax Slab for {currency} already exists: '{existing_slabs[0].name}'"
        )
        return existing_slabs[0].name

    try:
        slab = frappe.new_doc(slab_doctype)
        slab.slab_name = slab_name
        slab.company = company or ""
        slab.is_default = 1
        slab.enabled = 1
        slab.income_tax_slab_type = "Regular"
        slab.currency = currency
        slab.effective_from = getdate("2023-01-01")
        slab.flags.ignore_permissions = True
        slab.flags.ignore_mandatory = True

        # Add standard Indonesian tax brackets
        slab.append(
            "slabs",
            {"from_amount": 0, "to_amount": 60000000, "rate": 5, "fixed_amount": 0},
        )
        slab.append(
            "slabs",
            {
                "from_amount": 60000000,
                "to_amount": 250000000,
                "rate": 15,
                "fixed_amount": 0,
            },
        )
        slab.append(
            "slabs",
            {
                "from_amount": 250000000,
                "to_amount": 500000000,
                "rate": 25,
                "fixed_amount": 0,
            },
        )
        slab.append(
            "slabs",
            {
                "from_amount": 500000000,
                "to_amount": 5000000000,
                "rate": 30,
                "fixed_amount": 0,
            },
        )
        slab.append(
            "slabs",
            {"from_amount": 5000000000, "to_amount": 0, "rate": 35, "fixed_amount": 0},
        )

        slab.insert(ignore_permissions=True, ignore_mandatory=True)
        frappe.db.commit()
        logger.info(f"Created Income Tax Slab '{slab_name}' successfully.")
        return slab.name
    except Exception as e:
        frappe.db.rollback()
        logger.error(f"Error creating Income Tax Slab '{slab_name}': {str(e)}")
        frappe.log_error(
            f"Error creating Income Tax Slab '{slab_name}': {str(e)}\n{frappe.get_traceback()}",
            "Income Tax Slab Error",
        )
        return None


def _find_any_company_name() -> Optional[str]:
    """Return name of any Company, or None if none exists."""
    if not frappe.db.table_exists("Company"):
        return None
    return frappe.db.get_value("Company", {}, "name")


def get_default_tax_slab(create_if_missing=True) -> Optional[str]:
    """
    Get default Income Tax Slab for Indonesia (IDR). Create if missing.

    Returns:
        str: Name of the default slab, or None if not found/created.
    """
    slab_doctype = "Income Tax Slab"
    currency = "IDR"
    try:
        try:
            default_slab = frappe.db.get_value(
                slab_doctype, {"currency": currency, "is_default": 1}, "name"
            )
        except (DoesNotExistError, Exception) as e:
            # Column might not exist on fresh databases
            if "is_default" in str(e):
                logger.warning(
                    "'is_default' column missing in Income Tax Slab. Skipping filter."
                )
                default_slab = frappe.db.get_value(
                    slab_doctype, {"currency": currency}, "name"
                )
            else:
                raise
        if default_slab:
            return default_slab
        if create_if_missing:
            setup_income_tax_slab()
            try:
                default_slab = frappe.db.get_value(
                    slab_doctype, {"currency": currency, "is_default": 1}, "name"
                )
            except (DoesNotExistError, Exception) as e:
                if "is_default" in str(e):
                    logger.warning(
                        "'is_default' column missing in Income Tax Slab. Skipping filter."
                    )
                    default_slab = frappe.db.get_value(
                        slab_doctype, {"currency": currency}, "name"
                    )
                else:
                    raise
            return default_slab
        return None
    except Exception as e:
        logger.error(f"Error retrieving default tax slab: {str(e)}")
        return None


def update_salary_structures() -> int:
    """
    Update all Salary Structures to set default Income Tax Slab
    and bypass validation errors.

    Returns:
        int: Number of updated Salary Structures.
    """
    success_count = 0
    try:
        default_tax_slab = get_default_tax_slab()
        if not default_tax_slab:
            logger.error("Failed to get default tax slab")
            return 0

        structures = frappe.get_all(
            "Salary Structure", filters={"is_active": 1}, fields=["name", "docstatus"]
        )
        logger.info(f"Found {len(structures)} active salary structures to update")

        for structure in structures:
            try:
                if structure.docstatus == 0:
                    doc = frappe.get_doc("Salary Structure", structure.name)
                    doc.income_tax_slab = default_tax_slab
                    doc.tax_calculation_method = "Manual"
                    doc.flags.ignore_validate = True
                    doc.save(ignore_permissions=True)
                else:
                    frappe.db.set_value(
                        "Salary Structure",
                        structure.name,
                        {
                            "income_tax_slab": default_tax_slab,
                            "tax_calculation_method": "Manual",
                        },
                        update_modified=False,
                    )
                success_count += 1
            except Exception as e:
                frappe.log_error(
                    f"Error updating structure {structure.name}: {str(e)}",
                    "Salary Structure Update Error",
                )

        frappe.db.commit()
        logger.info(f"Updated {success_count} salary structures")
        return success_count

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            f"Critical error updating salary structures: {str(e)}", "Tax Slab Error"
        )
        return 0


def update_existing_assignments() -> int:
    """
    Update existing Salary Structure Assignments with default Income Tax Slab.

    Returns:
        int: Number of updated Salary Structure Assignments.
    """
    success_count = 0
    try:
        default_tax_slab = get_default_tax_slab()
        if not default_tax_slab:
            logger.error("Failed to get default tax slab")
            return 0

        assignments = frappe.get_all(
            "Salary Structure Assignment",
            filters=[["income_tax_slab", "in", ["", None]], ["docstatus", "=", 1]],
            fields=["name", "salary_structure"],
        )
        logger.info(f"Found {len(assignments)} salary structure assignments to update")

        # Find structures with PPh 21 component
        tax_structures = []
        try:
            query = """
                SELECT DISTINCT parent
                FROM `tabSalary Detail`
                WHERE salary_component = %s
                AND parenttype = %s
            """
            structures_with_tax = frappe.db.sql(
                query, ["PPh 21", "Salary Structure"], as_dict=1
            )
            if structures_with_tax:
                tax_structures = [s.parent for s in structures_with_tax]
        except Exception as e:
            frappe.log_error(
                f"Error finding salary structures with PPh 21: {str(e)}",
                "Tax Structure Query Error",
            )

        batch_size = 50
        for i in range(0, len(assignments), batch_size):
            batch = assignments[i : i + batch_size]
            for assignment in batch:
                try:
                    if assignment.salary_structure in tax_structures:
                        frappe.db.set_value(
                            "Salary Structure Assignment",
                            assignment.name,
                            "income_tax_slab",
                            default_tax_slab,
                            update_modified=False,
                        )
                        success_count += 1
                except Exception as e:
                    frappe.log_error(
                        f"Error updating assignment {assignment.name}: {str(e)}",
                        "Assignment Update Error",
                    )
                    continue
            frappe.db.commit()

        logger.info(f"Updated {success_count} salary structure assignments")
        return success_count

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            f"Error updating salary structure assignments: {str(e)}", "Tax Slab Error"
        )
        return 0
