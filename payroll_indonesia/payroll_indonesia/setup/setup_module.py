import json
import os
import traceback

import frappe

from payroll_indonesia.payroll_indonesia.setup.gl_account_mapper import (
    assign_gl_accounts_to_salary_components,
)
from payroll_indonesia.payroll_indonesia.setup.settings_migration import (
    setup_default_settings,
)


def resolve_template_fields(data: dict, company: str, abbr: str) -> dict:
    """
    Replace {{company}} and {{company_abbr}} in all string fields of a dict.
    """

    def render_val(val):
        if isinstance(val, str):
            val = val.replace("{{company}}", company).replace("{{company_abbr}}", abbr)
        return val

    return {k: render_val(v) for k, v in data.items()}


def create_account_if_not_exists(account_data: dict) -> None:
    """Create account if missing and log outcome."""
    company = account_data["company"]
    account_name = account_data["account_name"]

    frappe.logger().info(f"Attempting to create account {account_name} for {company}")

    existing = frappe.db.exists("Account", {"account_name": account_name, "company": company})
    if existing:
        frappe.logger().info(f"Account {account_name} already exists for {company}. Skipping.")
        return

    parent_account = account_data.get("parent_account")
    if parent_account and not frappe.db.exists("Account", parent_account):
        frappe.logger().warning(
            f"Parent account {parent_account} missing when creating {account_name} for {company}."
        )
        return

    doc = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": account_name,
            "parent_account": parent_account,
            "company": company,
            "root_type": account_data.get("root_type"),
            "account_type": account_data.get("account_type", ""),
            "is_group": account_data.get("is_group", 0),
            "report_type": account_data.get("report_type", "Profit and Loss"),
        }
    )
    doc.insert(ignore_permissions=True)
    frappe.logger().info(f"Created account {doc.name} for {company}")


def get_active_companies():
    """Return all active companies in the system."""
    return frappe.get_all("Company", fields=["name", "abbr"])


def setup_accounts_from_json():
    """Create GL accounts for all companies from template JSON."""
    json_path = os.path.join(os.path.dirname(__file__), "..", "default_gl_accounts.json")
    json_path = os.path.abspath(json_path)

    if not os.path.exists(json_path):
        frappe.logger().error(f"GL Accounts file not found: {json_path}")
        return

    try:
        with open(json_path, "r") as f:
            gl_accounts = json.load(f)
    except Exception as e:
        frappe.logger().error(
            f"Failed to load default_gl_accounts.json: {str(e)}\n{traceback.format_exc()}"
        )
        return

    if not isinstance(gl_accounts, list):
        frappe.logger().error("default_gl_accounts.json must contain a list of records")
        return

    # Ensure parent accounts first
    gl_accounts.sort(key=lambda x: 0 if x.get("is_group") else 1)

    companies = get_active_companies()

    for company in companies:
        company_name = company["name"]
        company_abbr = company["abbr"]
        frappe.logger().info(f"Setting up GL Accounts for {company_name}")
        for acc in gl_accounts:
            rendered = resolve_template_fields(acc, company_name, company_abbr)

            required = ["company", "account_name", "parent_account", "root_type"]
            if not all(rendered.get(r) for r in required):
                frappe.logger().warning(f"Incomplete account definition skipped: {acc}")
                continue

            rendered["company_abbr"] = company_abbr
            create_account_if_not_exists(rendered)


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
            frappe.logger().info(f"Created Salary Structure '{structure_name}' for {company_name}")
            frappe.msgprint(f"Created Salary Structure: {structure_name} for {company_name}")
        except Exception as e:
            frappe.logger().error(
                f"Error creating Salary Structure for {company_name}: {str(e)}\n{traceback.format_exc()}"
            )


def after_sync():
    """
    Called after app sync. Sets up Payroll Indonesia Settings, GL accounts from JSON,
    salary mapping, and settings for all companies.
    """
    frappe.logger().info("Running after_sync for payroll_indonesia")
    try:
        # 1. Setup GL Accounts from JSON (new logic)
        setup_accounts_from_json()

        companies = get_active_companies()
        if not companies:
            frappe.logger().warning("No active companies found. Skipping setup.")
            return

        for company in companies:
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
