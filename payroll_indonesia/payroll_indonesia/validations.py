# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-17 07:09:57 by dannyaudian

import frappe
from frappe import _


@frappe.whitelist()
def validate_employee_golongan(jabatan, golongan):
    """
    Validate that employee's golongan level does not exceed the maximum allowed for their jabatan

    Args:
        jabatan (str): The jabatan (position) code
        golongan (str): The golongan (grade) code

    Raises:
        frappe.ValidationError: If golongan level exceeds maximum allowed level
    """
    if not jabatan:
        frappe.throw(_("Jabatan is required"))

    if not golongan:
        frappe.throw(_("Golongan is required"))

    max_golongan = frappe.db.get_value("Jabatan", jabatan, "max_golongan")
    if not max_golongan:
        frappe.throw(_("Maximum Golongan not set for Jabatan {0}").format(jabatan))

    max_level = frappe.db.get_value("Golongan", max_golongan, "level")
    if not max_level:
        frappe.throw(_("Level not set for Golongan {0}").format(max_golongan))

    current_level = frappe.db.get_value("Golongan", golongan, "level")
    if not current_level:
        frappe.throw(_("Level not set for Golongan {0}").format(golongan))

    if current_level > max_level:
        frappe.throw(
            _(
                "Employee's Golongan level ({0}) cannot be higher than "
                "the maximum allowed level ({1}) for the selected Jabatan"
            ).format(current_level, max_level)
        )


@frappe.whitelist()
def validate_bpjs_account_mapping(company):
    """
    Validate that a BPJS Account Mapping exists for the given company

    Args:
        company (str): Company name

    Returns:
        dict: BPJS Account Mapping details if valid

    Raises:
        frappe.ValidationError: If mapping does not exist or is incomplete
    """
    if not company:
        frappe.throw(_("Company is required to validate BPJS Account Mapping"))

    # Check if mapping exists
    mapping_name = frappe.db.get_value("BPJS Account Mapping", {"company": company}, "name")
    if not mapping_name:
        frappe.throw(
            _("BPJS Account Mapping not found for company {0}. Please create one first.").format(
                company
            )
        )

    # Get the mapping document
    mapping = frappe.get_doc("BPJS Account Mapping", mapping_name)

    # Validate required accounts
    required_fields = ["employee_expense_account", "employer_expense_account", "payable_account"]

    missing_fields = []
    for field in required_fields:
        if not mapping.get(field):
            missing_fields.append(frappe.unscrub(field))

    if missing_fields:
        frappe.throw(
            _("The following required accounts are missing in BPJS Account Mapping: {0}").format(
                ", ".join(missing_fields)
            )
        )

    # Return the mapping if all validations pass
    return {
        "name": mapping.name,
        "employee_expense_account": mapping.employee_expense_account,
        "employer_expense_account": mapping.employer_expense_account,
        "payable_account": mapping.payable_account,
    }


@frappe.whitelist()
def validate_bpjs_components(company, salary_structure=None):
    """
    Validate that all required BPJS components exist in the salary structure

    Args:
        company (str): Company name
        salary_structure (str, optional): Salary Structure name to validate

    Returns:
        dict: Validation results

    Raises:
        frappe.ValidationError: If required components are missing
    """
    # First validate BPJS Account Mapping
    mapping = validate_bpjs_account_mapping(company)

    # Required BPJS components
    required_components = [
        "BPJS Kesehatan Employee",
        "BPJS JHT Employee",
        "BPJS JP Employee",
        "BPJS Kesehatan Employer",
        "BPJS JHT Employer",
        "BPJS JP Employer",
        "BPJS JKK",
        "BPJS JKM",
    ]

    # Check if all components exist
    missing_components = []
    for component in required_components:
        if not frappe.db.exists("Salary Component", component):
            missing_components.append(component)

    if missing_components:
        frappe.throw(
            _("The following BPJS components are missing: {0}").format(
                ", ".join(missing_components)
            )
        )

    # If salary structure is provided, validate components in structure
    if salary_structure:
        return validate_structure_components(salary_structure, required_components)

    return {"status": "success", "message": _("All BPJS components exist"), "mapping": mapping}


def validate_structure_components(salary_structure, required_components):
    """
    Validate that all required components exist in the given salary structure

    Args:
        salary_structure (str): Salary Structure name
        required_components (list): List of required component names

    Returns:
        dict: Validation results with missing components if any
    """
    if not frappe.db.exists("Salary Structure", salary_structure):
        frappe.throw(_("Salary Structure {0} does not exist").format(salary_structure))

    structure = frappe.get_doc("Salary Structure", salary_structure)

    # Get all components in the structure
    structure_components = []
    if hasattr(structure, "earnings"):
        structure_components.extend([d.salary_component for d in structure.earnings])
    if hasattr(structure, "deductions"):
        structure_components.extend([d.salary_component for d in structure.deductions])

    # Find missing components
    missing_in_structure = []
    for component in required_components:
        if component not in structure_components:
            missing_in_structure.append(component)

    if missing_in_structure:
        return {
            "status": "warning",
            "message": _("Some BPJS components are missing in the salary structure"),
            "missing_components": missing_in_structure,
        }

    return {
        "status": "success",
        "message": _("All required BPJS components exist in the salary structure"),
    }
