import os
import json
import traceback

import frappe
from payroll_indonesia.payroll_indonesia.setup.gl_account_mapper import (
    assign_gl_accounts_to_salary_components,
)
from payroll_indonesia.payroll_indonesia.setup.settings_migration import (
    setup_default_settings,
)


def get_active_companies():
    """Return all active companies in the system."""
    return frappe.get_all("Company", filters={"disabled": 0}, fields=["name", "abbr"])


def get_or_create_parent_account(company_name, company_abbr, account_name, root_type):
    """
    Ensure parent account exists for the company. Return full account name with abbr.
    """
    full_account_name = f"{account_name} - {company_abbr}"
    if frappe.db.exists("Account", full_account_name):
        return full_account_name
    try:
        parent_doc = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": account_name,
                "company": company_name,
                "is_group": 1,
                "root_type": root_type,
                "report_type": "Profit and Loss" if root_type == "Expense" else "Balance Sheet",
            }
        )
        parent_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.logger().info(f"Created parent account {full_account_name} for {company_name}")
        return full_account_name
    except Exception as e:
        frappe.logger().error(
            f"Error creating parent account {full_account_name} for {company_name}: {str(e)}\n{traceback.format_exc()}"
        )
        return None


def create_account_if_not_exists(
    company_name,
    company_abbr,
    account_name,
    root_type,
    account_type,
    is_group,
    parent_account,
):
    """
    Create an account if it does not exist for the company. Defensive error handling.
    """
    full_account_name = f"{account_name} - {company_abbr}"
    if frappe.db.exists("Account", full_account_name):
        frappe.logger().info(f"Account {full_account_name} already exists for {company_name}. Skipping.")
        return
    if not frappe.db.exists("Account", parent_account):
        frappe.logger().error(
            f"Parent account {parent_account} missing for child {full_account_name} in company {company_name}. Skipping."
        )
        return
    try:
        account_doc = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": account_name,
                "parent_account": parent_account,
                "company": company_name,
                "root_type": root_type,
                "account_type": account_type,
                "is_group": is_group,
                "report_type": "Profit and Loss" if root_type == "Expense" else "Balance Sheet",
            }
        )
        account_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.logger().info(f"Created account {full_account_name} under {parent_account} for {company_name}")
    except Exception as e:
        frappe.logger().error(
            f"Error creating account {full_account_name} in {company_name}: {str(e)}\n{traceback.format_exc()}"
        )


def setup_accounts_for_company(company):
    """
    Setup all default GL accounts for a single company. Modular & idempotent.
    """
    company_name = company["name"]
    company_abbr = company["abbr"]

    json_path = os.path.join(
        frappe.get_app_path("payroll_indonesia"),
        "payroll_indonesia",
        "data",
        "default_gl_accounts.json",
    )
    if not os.path.exists(json_path):
        frappe.logger().error(f"File not found: {json_path}")
        return

    try:
        with open(json_path, "r") as f:
            gl_accounts = json.load(f)
    except Exception as e:
        frappe.logger().error(
            f"Failed to load default_gl_accounts.json: {str(e)}\n{traceback.format_exc()}"
        )
        return

    # Ensure parent accounts first
    parent_expense = get_or_create_parent_account(company_name, company_abbr, "Direct Expenses", "Expense")
    parent_liability = get_or_create_parent_account(company_name, company_abbr, "Duties and Taxes", "Liability")

    for acc in gl_accounts:
        account_name = acc.get("account_name")
        root_type = acc.get("root_type")
        account_type = acc.get("account_type")
        is_group = acc.get("is_group", 0)
        category = acc.get("category") or "expense"

        # Determine parent based on category
        if category == "expense":
            parent_account = parent_expense
        elif category == "liability":
            parent_account = parent_liability
        else:
            frappe.logger().error(
                f"Unknown category '{category}' for account '{account_name}' in company '{company_name}'. Skipping."
            )
            continue

        if not parent_account:
            frappe.logger().error(
                f"Missing parent account for category '{category}' in company '{company_name}'. Skipping '{account_name}'."
            )
            continue

        create_account_if_not_exists(
            company_name=company_name,
            company_abbr=company_abbr,
            account_name=account_name,
            root_type=root_type,
            account_type=account_type,
            is_group=is_group,
            parent_account=parent_account,
        )


def create_salary_structure_for_company(company_name):
    """
    Create Salary Structure for Indonesian Payroll Standard for the company if not exists.
    The structure and components are loaded from salary_structure.json fixture file.
    """
    json_file_path = frappe.get_app_path("payroll_indonesia", "setup", "salary_structure.json")
    if not os.path.exists(json_file_path):
        frappe.log_error(f"File not found: {json_file_path}", "Payroll Indonesia Setup")
        return

    try:
        with open(json_file_path, "r") as f:
            salary_structures = json.load(f)
    except Exception as e:
        frappe.logger().error(
            f"Failed to load salary_structure.json: {str(e)}\n{traceback.format_exc()}"
        )
        return

    for structure in salary_structures:
        structure_name = structure.get(
            "salary_structure_name", structure.get("name", "Indonesian Payroll Standard")
        )
        exists = frappe.db.exists(
            "Salary Structure", {"salary_structure_name": structure_name, "company": company_name}
        )
        if exists:
            frappe.logger().info(
                f"Salary Structure '{structure_name}' already exists for {company_name}. Skipping."
            )
            continue

        doc = frappe.get_doc(
            {
                "doctype": "Salary Structure",
                "salary_structure_name": structure_name,
                "company": company_name,
                "is_active": 1,
                "payroll_frequency": "Monthly",
                "remarks": "Salary Structure Payroll Indonesia sesuai regulasi PPh 21, BPJS dan PMK terbaru.",
                "earnings": [
                    {"salary_component": e["salary_component"]}
                    for e in structure.get("earnings", [])
                ],
                "deductions": [
                    {"salary_component": d["salary_component"]}
                    for d in structure.get("deductions", [])
                ],
                "salary_structure_assignments": structure.get("salary_structure_assignments", []),
            }
        )
        try:
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.logger().info(
                f"Created Salary Structure '{structure_name}' for {company_name}"
            )
            frappe.msgprint(f"Created Salary Structure: {structure_name} for {company_name}")
        except Exception as e:
            frappe.logger().error(
                f"Error creating Salary Structure for {company_name}: {str(e)}\n{traceback.format_exc()}"
            )


def after_sync():
    """
    Called after app sync. Sets up default GL accounts, salary mapping, and settings for all companies.
    """
    try:
        companies = get_active_companies()
        if not companies:
            frappe.logger().warning("No active companies found. Skipping setup.")
            return

        for company in companies:
            try:
                setup_accounts_for_company(company)
            except Exception as e:
                frappe.logger().error(
                    f"Error in setup_accounts_for_company for {company['name']}: {str(e)}\n{traceback.format_exc()}"
                )

            try:
                assign_gl_accounts_to_salary_components(company["name"], company["abbr"])
                frappe.logger().info(
                    f"Mapped salary components to GL accounts for company: {company['name']}"
                )
            except Exception as e:
                frappe.logger().error(
                    f"Error mapping salary components to GL accounts for company {company['name']}: {str(e)}\n{traceback.format_exc()}"
                )

            try:
                create_salary_structure_for_company(company["name"])
            except Exception as e:
                frappe.logger().error(
                    f"Error creating Salary Structure for company {company['name']}: {str(e)}\n{traceback.format_exc()}"
                )

        try:
            setup_default_settings()
            frappe.logger().info("Payroll Indonesia Settings tables migrated (PTKP/TER/Brackets)")
        except Exception as e:
            frappe.logger().error(
                f"Error in Payroll Indonesia Settings migration: {str(e)}\n{traceback.format_exc()}"
            )

        frappe.msgprint(
            "Payroll Indonesia: Default GL accounts setup, salary structure, mapping, and settings migration completed"
        )

    except Exception as e:
        frappe.logger().error(
            f"Error in Payroll Indonesia after_sync setup: {str(e)}\n{traceback.format_exc()}"
        )