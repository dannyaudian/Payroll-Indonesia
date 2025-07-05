# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 09:20:06 by dannyaudian

import frappe
from frappe import _
from frappe.utils import getdate
from payroll_indonesia.frappe_helpers import logger

__all__ = [
    "create_default_tax_slab",
    "create_income_tax_slab",
    "get_default_tax_slab",
    "update_salary_structures",
    "update_existing_assignments",
]


def create_default_tax_slab():
    """
    Function for compatibility - calls create_income_tax_slab().

    Returns:
        str: Name of the Income Tax Slab or None if creation failed.
    """
    return create_income_tax_slab()


def create_income_tax_slab():
    """
    Create Income Tax Slab for Indonesia.

    Returns:
        str: Name of the created or existing Income Tax Slab.

    Raises:
        frappe.ValidationError: If tax slab creation fails and no fallback exists.
    """
    try:
        # Check if already exists
        existing_slabs = frappe.get_all(
            "Income Tax Slab", filters={"currency": "IDR"}, fields=["name"]
        )
        if existing_slabs:
            logger.info(f"Income Tax Slab for IDR already exists: {existing_slabs[0].name}")
            return existing_slabs[0].name

        # Get company
        company = frappe.defaults.get_defaults().get("company")
        if not company:
            companies = frappe.get_all("Company", fields=["name"])
            if companies:
                company = companies[0].name
            else:
                logger.error("No company found, cannot create Income Tax Slab")
                raise frappe.ValidationError(_("No company found to associate with tax slab"))

        # Create tax slab
        tax_slab = frappe.new_doc("Income Tax Slab")
        tax_slab.title = "Indonesia Income Tax"
        tax_slab.effective_from = getdate("2023-01-01")
        tax_slab.company = company
        tax_slab.currency = "IDR"
        tax_slab.income_tax_slab_name = "Indonesia Income Tax"
        tax_slab.is_default = 1
        tax_slab.disabled = 0

        # Add tax brackets
        tax_slab.append("slabs", {"from_amount": 0, "to_amount": 60000000, "percent_deduction": 5})
        tax_slab.append(
            "slabs", {"from_amount": 60000000, "to_amount": 250000000, "percent_deduction": 15}
        )
        tax_slab.append(
            "slabs", {"from_amount": 250000000, "to_amount": 500000000, "percent_deduction": 25}
        )
        tax_slab.append(
            "slabs", {"from_amount": 500000000, "to_amount": 5000000000, "percent_deduction": 30}
        )
        tax_slab.append(
            "slabs", {"from_amount": 5000000000, "to_amount": 0, "percent_deduction": 35}
        )

        # Save with flags to bypass validation
        tax_slab.flags.ignore_permissions = True
        tax_slab.flags.ignore_mandatory = True
        tax_slab.insert()
        frappe.db.commit()

        logger.info(f"Successfully created Income Tax Slab: {tax_slab.name}")
        return tax_slab.name

    except Exception as e:
        frappe.db.rollback()
        logger.error(f"Error creating Income Tax Slab: {str(e)}")
        frappe.log_error(f"Error creating Income Tax Slab: {str(e)}", "Tax Slab Error")

        # Last resort - check if any tax slabs exist already
        try:
            existing_slabs = frappe.get_all("Income Tax Slab", limit=1)
            if existing_slabs:
                logger.info(f"Using existing tax slab as last resort: {existing_slabs[0].name}")
                return existing_slabs[0].name
        except Exception as fallback_error:
            frappe.log_error(
                f"Failed to find fallback tax slab: {str(fallback_error)}", "Tax Slab Error"
            )

        # If we reach here, we have no tax slab - raise error for proper handling
        raise frappe.ValidationError(_("Failed to create or find valid Income Tax Slab"))


def get_default_tax_slab(create_if_missing=True):
    """
    Get default Income Tax Slab for Indonesia.

    Args:
        create_if_missing: Create tax slab if none exists.

    Returns:
        str: Name of the default Income Tax Slab.

    Raises:
        frappe.ValidationError: If no slab can be found or created.
    """
    try:
        # Check if we have a default slab
        default_slab = None

        # Get default slab if is_default field exists
        try:
            default_slab = frappe.db.get_value(
                "Income Tax Slab", {"currency": "IDR", "is_default": 1}, "name"
            )
        except Exception as field_error:
            frappe.log_error(
                f"Error checking default tax slab: {str(field_error)}", "Tax Slab Field Error"
            )

        # If no default slab, get any IDR slab
        if not default_slab:
            slabs = frappe.get_all(
                "Income Tax Slab",
                filters={"currency": "IDR"},
                fields=["name"],
                order_by="effective_from desc",
                limit=1,
            )

            if slabs:
                default_slab = slabs[0].name

        # If still no slab and create_if_missing is True, create one
        if not default_slab and create_if_missing:
            default_slab = create_income_tax_slab()

        if not default_slab:
            raise frappe.ValidationError(_("Could not find or create a valid Income Tax Slab"))

        return default_slab

    except frappe.ValidationError:
        # Re-raise validation errors for proper handling
        raise
    except Exception as e:
        frappe.log_error(f"Error getting default tax slab: {str(e)}", "Tax Slab Error")
        raise frappe.ValidationError(_("Error retrieving Income Tax Slab"))


def update_salary_structures():
    """
    Update all Salary Structures to bypass Income Tax Slab validation
    with improved error handling for missing salary details.

    Returns:
        int: Number of successfully updated Salary Structures.
    """
    success_count = 0

    try:
        # Get default tax slab
        default_tax_slab = get_default_tax_slab()
        if not default_tax_slab:
            logger.error("Failed to get default tax slab")
            return 0

        # Get active salary structures
        structures = frappe.get_all(
            "Salary Structure", filters={"is_active": 1}, fields=["name", "docstatus"]
        )

        logger.info(f"Found {len(structures)} active salary structures to update")

        # Update each structure
        for structure in structures:
            try:
                # Only update if it's not submitted
                if structure.docstatus == 0:
                    # Update the structure
                    doc = frappe.get_doc("Salary Structure", structure.name)
                    doc.income_tax_slab = default_tax_slab
                    doc.tax_calculation_method = "Manual"
                    doc.flags.ignore_validate = True  # Skip validation
                    doc.save(ignore_permissions=True)
                    success_count += 1
                else:
                    # For submitted documents, use direct DB update
                    frappe.db.set_value(
                        "Salary Structure",
                        structure.name,
                        {"income_tax_slab": default_tax_slab, "tax_calculation_method": "Manual"},
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
        frappe.log_error(f"Critical error updating salary structures: {str(e)}", "Tax Slab Error")
        return 0


def update_existing_assignments():
    """
    Update existing Salary Structure Assignments with default Income Tax Slab
    to bypass validation errors.

    Returns:
        int: Number of successfully updated Salary Structure Assignments.
    """
    success_count = 0

    try:
        # Get default tax slab
        default_tax_slab = get_default_tax_slab()
        if not default_tax_slab:
            logger.error("Failed to get default tax slab")
            return 0

        # Get assignments needing update
        assignments = frappe.get_all(
            "Salary Structure Assignment",
            filters=[["income_tax_slab", "in", ["", None]], ["docstatus", "=", 1]],
            fields=["name", "salary_structure"],
        )

        logger.info(f"Found {len(assignments)} salary structure assignments to update")

        # Find structures with PPh 21 component - using parameterized query
        tax_structures = []
        try:
            query = """
                SELECT DISTINCT parent
                FROM `tabSalary Detail`
                WHERE salary_component = %s
                AND parenttype = %s
            """
            structures_with_tax = frappe.db.sql(query, ["PPh 21", "Salary Structure"], as_dict=1)

            if structures_with_tax:
                tax_structures = [s.parent for s in structures_with_tax]
        except Exception as e:
            frappe.log_error(
                f"Error finding salary structures with PPh 21: {str(e)}",
                "Tax Structure Query Error",
            )

        # Process assignments
        batch_size = 50
        for i in range(0, len(assignments), batch_size):
            batch = assignments[i : i + batch_size]
            updated_in_batch = 0

            for assignment in batch:
                try:
                    # Only update if the structure has PPh 21 component
                    if assignment.salary_structure in tax_structures:
                        frappe.db.set_value(
                            "Salary Structure Assignment",
                            assignment.name,
                            "income_tax_slab",
                            default_tax_slab,
                            update_modified=False,
                        )
                        updated_in_batch += 1
                        success_count += 1
                except Exception as e:
                    frappe.log_error(
                        f"Error updating assignment {assignment.name}: {str(e)}",
                        "Assignment Update Error",
                    )
                    continue

            # Commit after each batch
            frappe.db.commit()

        logger.info(f"Updated {success_count} salary structure assignments")
        return success_count

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"Error updating salary structure assignments: {str(e)}", "Tax Slab Error")
        return 0
