# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-17 07:16:30 by dannyaudian

import frappe

# from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.utils import now_datetime

__all__ = [
    "fix_bpjs_payment_summary",
    "fix_bpjs_account_mapping",
    "check_bpjs_payment_details",
    "check_child_table_fields",
    "create_custom_child_doctype",
    "run",
    "diagnose_doctype_structure",
    "log_error",
]


def run():
    """
    Main function to fix all BPJS-related DocTypes
    Can be called from patches or console

    Returns:
        dict: Status of fixed DocTypes
    """
    timestamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    results = {
        "timestamp": timestamp,
        "bpjs_payment_summary": False,
        "bpjs_account_mapping": False,
        "success": False,
    }

    try:
        frappe.logger().info(f"[{timestamp}] Starting BPJS DocType structure fixes")

        # Fix BPJS Payment Summary and related child tables
        results["bpjs_payment_summary"] = fix_bpjs_payment_summary()

        # Fix BPJS Account Mapping
        results["bpjs_account_mapping"] = fix_bpjs_account_mapping()

        # Set overall success
        results["success"] = results["bpjs_payment_summary"] and results["bpjs_account_mapping"]

        frappe.logger().info(f"[{timestamp}] BPJS DocType structure fixes completed")
        return results

    except Exception as e:
        log_error(f"Error fixing BPJS DocTypes: {str(e)}", "DocType Fix Error")
        results["error"] = str(e)
        return results


def fix_bpjs_payment_summary():
    """
    Fix BPJS Payment Summary structure by adding custom fields if needed

    Returns:
        bool: True if successful, False if error occurred
    """
    try:
        frappe.logger().info("Checking BPJS Payment Summary DocType structure...")

        if not frappe.db.exists("DocType", "BPJS Payment Summary"):
            frappe.logger().error("BPJS Payment Summary DocType not found.")
            return False

        # Check required fields using custom field approach
        required_fields = {
            "month": {"fieldtype": "Int", "label": "Month", "insert_after": "company"},
            "year": {"fieldtype": "Int", "label": "Year", "insert_after": "month"},
            "month_year": {"fieldtype": "Data", "label": "Month-Year", "insert_after": "year"},
            "month_name": {
                "fieldtype": "Data",
                "label": "Month Name",
                "insert_after": "month_year",
            },
            "month_year_title": {
                "fieldtype": "Data",
                "label": "Title",
                "insert_after": "month_name",
            },
            "total_employee": {
                "fieldtype": "Currency",
                "label": "Total Employee Share",
                "insert_after": "month_year_title",
            },
            "total_employer": {
                "fieldtype": "Currency",
                "label": "Total Employer Share",
                "insert_after": "total_employee",
            },
            "grand_total": {
                "fieldtype": "Currency",
                "label": "Grand Total",
                "insert_after": "total_employer",
            },
            "payment_entry": {
                "fieldtype": "Link",
                "label": "Payment Entry",
                "options": "Payment Entry",
                "insert_after": "grand_total",
            },
        }

        # Check if fields exist already
        docfields = frappe.get_meta("BPJS Payment Summary").fields
        existing_fields = [df.fieldname for df in docfields]
        missing_fields = [f for f in required_fields.keys() if f not in existing_fields]

        if missing_fields:
            frappe.logger().info(
                f"Missing fields detected in BPJS Payment Summary: {', '.join(missing_fields)}"
            )

            # Create custom fields for missing fields
            for field_name in missing_fields:
                field_def = required_fields[field_name]

                try:
                    create_custom_field(
                        "BPJS Payment Summary",
                        {
                            "fieldname": field_name,
                            "fieldtype": field_def["fieldtype"],
                            "label": field_def["label"],
                            "insert_after": field_def["insert_after"],
                            "options": field_def.get("options", ""),
                        },
                    )
                    frappe.logger().info(f"Added field '{field_name}' to BPJS Payment Summary.")
                except Exception as e:
                    log_error(
                        f"Error creating custom field {field_name}: {str(e)}",
                        "Custom Field Creation Error",
                    )
        else:
            frappe.logger().info("BPJS Payment Summary structure is OK.")

        # Check child table
        check_bpjs_payment_details()
        return True

    except Exception as e:
        log_error(f"Error fixing BPJS Payment Summary: {str(e)}", "DocType Fix Error")
        return False


def check_bpjs_payment_details():
    """
    Check and fix the structure of BPJS Payment Details child table

    Returns:
        bool: True if successful, False if error occurred
    """
    try:
        # Find the child table DocType name
        child_table_fieldname = None
        parent_meta = frappe.get_meta("BPJS Payment Summary")

        for field in parent_meta.fields:
            if field.fieldtype == "Table" and (
                "summary_details" in field.fieldname or "details" in field.fieldname
            ):
                child_table_fieldname = field.fieldname
                child_doctype_name = field.options
                break

        if not child_table_fieldname:
            # Create a custom link field for the child table relationship
            frappe.logger().info("Creating summary_details table field in BPJS Payment Summary")

            create_custom_field(
                "BPJS Payment Summary",
                {
                    "fieldname": "summary_details_section",
                    "fieldtype": "Section Break",
                    "label": "Payment Details",
                    "insert_after": "payment_entry",
                },
            )

            # Check if we can find or create a child DocType
            child_doctype_name = "BPJS Payment Summary Detail"
            if not frappe.db.exists("DocType", child_doctype_name):
                frappe.logger().info(
                    f"Child table DocType {child_doctype_name} not found. Creating it..."
                )
                child_doctype_name = create_custom_child_doctype(child_doctype_name)
                if not child_doctype_name:
                    return False

            # Create the table field
            create_custom_field(
                "BPJS Payment Summary",
                {
                    "fieldname": "summary_details",
                    "fieldtype": "Table",
                    "label": "Payment Details",
                    "options": child_doctype_name,
                    "insert_after": "summary_details_section",
                },
            )
            frappe.logger().info(
                f"Created summary_details table field linked to {child_doctype_name}"
            )

        # Check fields in the child table
        if child_doctype_name and frappe.db.exists("DocType", child_doctype_name):
            check_child_table_fields(child_doctype_name)
            return True

        return False

    except Exception as e:
        log_error(
            f"Error checking BPJS Payment Details structure: {str(e)}",
            "DocType Structure Check Error",
        )
        return False


def check_child_table_fields(child_doctype_name):
    """
    Check and add missing fields to child table via custom fields

    Args:
        child_doctype_name (str): Name of child DocType to check and fix

    Returns:
        bool: True if successful, False if error occurred
    """
    try:
        child_meta = frappe.get_meta(child_doctype_name)
        existing_fields = [df.fieldname for df in child_meta.fields]

        required_fields = {
            "employee": {
                "fieldtype": "Link",
                "label": "Employee",
                "options": "Employee",
                "insert_after": "idx",
                "reqd": 1,
            },
            "employee_name": {
                "fieldtype": "Data",
                "label": "Employee Name",
                "insert_after": "employee",
                "fetch_from": "employee.employee_name",
            },
            "salary_slip": {
                "fieldtype": "Link",
                "label": "Salary Slip",
                "options": "Salary Slip",
                "insert_after": "employee_name",
            },
            "employee_share": {
                "fieldtype": "Currency",
                "label": "Employee Share",
                "insert_after": "salary_slip",
            },
            "employer_share": {
                "fieldtype": "Currency",
                "label": "Employer Share",
                "insert_after": "employee_share",
            },
            "total": {
                "fieldtype": "Currency",
                "label": "Total",
                "insert_after": "employer_share",
            },
        }

        missing_fields = [f for f in required_fields.keys() if f not in existing_fields]

        if missing_fields:
            frappe.logger().info(
                f"Missing fields detected in {child_doctype_name}: {', '.join(missing_fields)}"
            )

            # For child table, if it's a custom DocType, we can directly add the fields
            is_custom = frappe.db.get_value("DocType", child_doctype_name, "custom")

            if is_custom:
                # Add fields directly to the custom DocType
                for field_name in missing_fields:
                    field_def = required_fields[field_name]

                    try:
                        # Get DocType and add field
                        doc = frappe.get_doc("DocType", child_doctype_name)
                        field = doc.append("fields", {})
                        field.fieldname = field_name
                        field.fieldtype = field_def["fieldtype"]
                        field.label = field_def["label"]

                        if "options" in field_def:
                            field.options = field_def["options"]
                        if "reqd" in field_def:
                            field.reqd = field_def["reqd"]
                        if "fetch_from" in field_def:
                            field.fetch_from = field_def["fetch_from"]

                        doc.save()
                        frappe.logger().info(f"Added field '{field_name}' to {child_doctype_name}")
                    except Exception as e:
                        log_error(
                            f"Error adding field {field_name}: {str(e)}", "Field Addition Error"
                        )
            else:
                frappe.logger().warning(
                    "Cannot modify standard child table directly. "
                    "Please create a custom child DocType with all required fields."
                )
        else:
            frappe.logger().info(f"{child_doctype_name} structure is OK.")

        return True

    except Exception as e:
        log_error(
            f"Error checking child table fields for {child_doctype_name}: {str(e)}",
            "Child Table Check Error",
        )
        return False


def create_custom_child_doctype(doctype_name):
    """
    Create a new custom child DocType with all required fields

    Args:
        doctype_name (str): Name of the child DocType to create

    Returns:
        str: Name of created DocType if successful, None if failed
    """
    try:
        if frappe.db.exists("DocType", doctype_name):
            frappe.logger().info(f"{doctype_name} already exists.")
            return doctype_name

        # Create custom DocType
        doc = frappe.new_doc("DocType")
        doc.name = doctype_name
        doc.module = "Payroll Indonesia"
        doc.custom = 1  # Mark as custom
        doc.istable = 1
        doc.editable_grid = 1
        doc.track_changes = 0

        # Add fields
        fields = [
            {
                "fieldname": "employee",
                "fieldtype": "Link",
                "label": "Employee",
                "options": "Employee",
                "reqd": 1,
                "in_list_view": 1,
            },
            {
                "fieldname": "employee_name",
                "fieldtype": "Data",
                "label": "Employee Name",
                "fetch_from": "employee.employee_name",
                "in_list_view": 1,
            },
            {
                "fieldname": "salary_slip",
                "fieldtype": "Link",
                "label": "Salary Slip",
                "options": "Salary Slip",
            },
            {
                "fieldname": "employee_share",
                "fieldtype": "Currency",
                "label": "Employee Share",
                "in_list_view": 1,
            },
            {
                "fieldname": "employer_share",
                "fieldtype": "Currency",
                "label": "Employer Share",
                "in_list_view": 1,
            },
            {
                "fieldname": "total",
                "fieldtype": "Currency",
                "label": "Total",
                "in_list_view": 1,
            },
        ]

        for field_def in fields:
            field = doc.append("fields", {})
            field.fieldname = field_def["fieldname"]
            field.fieldtype = field_def["fieldtype"]
            field.label = field_def["label"]

            if "options" in field_def:
                field.options = field_def["options"]

            if "reqd" in field_def:
                field.reqd = field_def["reqd"]

            if "in_list_view" in field_def:
                field.in_list_view = field_def["in_list_view"]

            if "fetch_from" in field_def:
                field.fetch_from = field_def["fetch_from"]

        # Save DocType
        doc.insert()
        frappe.logger().info(f"Created new custom DocType: {doctype_name}")
        return doctype_name

    except Exception as e:
        log_error(f"Error creating {doctype_name} DocType: {str(e)}", "DocType Creation Error")
        return None


def fix_bpjs_account_mapping():
    """
    Fix BPJS Account Mapping structure by adding required fields if missing

    Returns:
        bool: True if successful, False if error occurred
    """
    try:
        frappe.logger().info("Checking BPJS Account Mapping DocType structure...")

        if not frappe.db.exists("DocType", "BPJS Account Mapping"):
            frappe.logger().error("BPJS Account Mapping DocType not found.")
            return False

        # Check required fields using custom field approach
        required_fields = {
            "company": {
                "fieldtype": "Link",
                "label": "Company",
                "options": "Company",
                "reqd": 1,
                "insert_after": "mapping_name",
            },
            "employee_expense_account": {
                "fieldtype": "Link",
                "label": "Employee Expense Account",
                "options": "Account",
                "insert_after": "company",
            },
            "employer_expense_account": {
                "fieldtype": "Link",
                "label": "Employer Expense Account",
                "options": "Account",
                "insert_after": "employee_expense_account",
            },
            "payable_account": {
                "fieldtype": "Link",
                "label": "Payable Account",
                "options": "Account",
                "insert_after": "employer_expense_account",
            },
        }

        # Check if fields exist already
        docfields = frappe.get_meta("BPJS Account Mapping").fields
        existing_fields = [df.fieldname for df in docfields]
        missing_fields = [f for f in required_fields.keys() if f not in existing_fields]

        if missing_fields:
            frappe.logger().info(
                f"Missing fields detected in BPJS Account Mapping: {', '.join(missing_fields)}"
            )

            # Create custom fields for missing fields
            for field_name in missing_fields:
                field_def = required_fields[field_name]

                try:
                    create_custom_field(
                        "BPJS Account Mapping",
                        {
                            "fieldname": field_name,
                            "fieldtype": field_def["fieldtype"],
                            "label": field_def["label"],
                            "options": field_def.get("options", ""),
                            "reqd": field_def.get("reqd", 0),
                            "insert_after": field_def["insert_after"],
                        },
                    )
                    frappe.logger().info(f"Added field '{field_name}' to BPJS Account Mapping.")
                except Exception as e:
                    log_error(
                        f"Error creating custom field {field_name}: {str(e)}",
                        "Custom Field Creation Error",
                    )
        else:
            frappe.logger().info("BPJS Account Mapping structure is OK.")

        return True

    except Exception as e:
        log_error(f"Error fixing BPJS Account Mapping: {str(e)}", "DocType Fix Error")
        return False


def diagnose_doctype_structure():
    """
    Diagnose structure of BPJS-related DocTypes

    Returns:
        dict: Diagnostic information about DocType structure
    """
    results = {
        "timestamp": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
        "bpjs_payment_summary": {
            "exists": False,
            "missing_fields": [],
            "child_table_status": "Not Found",
        },
        "bpjs_account_mapping": {
            "exists": False,
            "missing_fields": [],
        },
    }

    try:
        # Check BPJS Payment Summary
        if frappe.db.exists("DocType", "BPJS Payment Summary"):
            results["bpjs_payment_summary"]["exists"] = True

            # Check required fields
            bpjs_required_fields = [
                "month",
                "year",
                "month_year",
                "month_name",
                "month_year_title",
                "total_employee",
                "total_employer",
                "grand_total",
                "payment_entry",
            ]
            docfields = frappe.get_meta("BPJS Payment Summary").fields
            existing_fields = [df.fieldname for df in docfields]

            results["bpjs_payment_summary"]["missing_fields"] = [
                f for f in bpjs_required_fields if f not in existing_fields
            ]

            # Check child table
            child_table_found = False
            child_table_name = None

            for field in docfields:
                if field.fieldtype == "Table" and (
                    "summary_details" in field.fieldname or "details" in field.fieldname
                ):
                    child_table_found = True
                    child_table_name = field.options
                    break

            if child_table_found and child_table_name:
                results["bpjs_payment_summary"]["child_table_status"] = {
                    "name": child_table_name,
                    "exists": frappe.db.exists("DocType", child_table_name),
                }
            else:
                results["bpjs_payment_summary"]["child_table_status"] = "Missing"

        # Check BPJS Account Mapping
        if frappe.db.exists("DocType", "BPJS Account Mapping"):
            results["bpjs_account_mapping"]["exists"] = True

            # Check required fields
            required_fields = [
                "company",
                "employee_expense_account",
                "employer_expense_account",
                "payable_account",
            ]
            docfields = frappe.get_meta("BPJS Account Mapping").fields
            existing_fields = [df.fieldname for df in docfields]

            results["bpjs_account_mapping"]["missing_fields"] = [
                f for f in required_fields if f not in existing_fields
            ]

        # Output diagnostic info
        frappe.logger().info("\nBPJS DocType Structure Diagnosis:")

        frappe.logger().info("\n1. BPJS Payment Summary:")
        if results["bpjs_payment_summary"]["exists"]:
            frappe.logger().info("   - Status: Exists")
            if results["bpjs_payment_summary"]["missing_fields"]:
                frappe.logger().info(
                    f"   - Missing fields: {', '.join(results['bpjs_payment_summary']['missing_fields'])}"
                )
            else:
                frappe.logger().info("   - All required fields present")

            frappe.logger().info(
                f"   - Child table: {results['bpjs_payment_summary']['child_table_status']}"
            )
        else:
            frappe.logger().info("   - Status: Not found")

        frappe.logger().info("\n2. BPJS Account Mapping:")
        if results["bpjs_account_mapping"]["exists"]:
            frappe.logger().info("   - Status: Exists")
            if results["bpjs_account_mapping"]["missing_fields"]:
                frappe.logger().info(
                    f"   - Missing fields: {', '.join(results['bpjs_account_mapping']['missing_fields'])}"
                )
            else:
                frappe.logger().info("   - All required fields present")
        else:
            frappe.logger().info("   - Status: Not found")

        return results

    except Exception as e:
        error_message = f"Error in diagnose_doctype_structure: {str(e)}"
        log_error(error_message, "DocType Diagnosis Error")
        return {"error": str(e), "timestamp": results["timestamp"]}


def log_error(message, title):
    """
    Log error with consistent format and full traceback

    Args:
        message (str): Error message
        title (str): Error title for the log
    """
    full_traceback = f"{message}\n\nTraceback: {frappe.get_traceback()}"
    frappe.log_error(full_traceback, title)
    timestamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    frappe.logger().error(f"[{timestamp}] [{title}] {message}")


# Run from bench console:
# from payroll_indonesia.utilities.fix_doctype_structure import run
# run()
