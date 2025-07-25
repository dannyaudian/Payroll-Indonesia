import json
import os
from typing import List, Optional

import frappe
from payroll_indonesia.payroll_indonesia.setup.gl_account_mapper import (
    assign_gl_accounts_to_salary_components,
)
from payroll_indonesia.payroll_indonesia.setup.settings_migration import setup_default_settings


def get_parent_account(possible_names: List[str], company_abbr: str) -> Optional[str]:
    """
    Find a suitable parent account by trying different possible names.
    """
    for name in possible_names:
        parent_account = f"{name} - {company_abbr}"
        if frappe.db.exists("Account", parent_account):
            return parent_account
    return None


def ensure_parent_account(
    name: str, company_name: str, company_abbr: str, root_type: str
) -> None:
    """Ensure a group parent account exists for the given company."""
    account_name_with_abbr = f"{name} - {company_abbr}"
    if frappe.db.exists("Account", account_name_with_abbr):
        return

    try:
        parent_doc = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": name,
                "company": company_name,
                "is_group": 1,
                "root_type": root_type,
                "report_type": "Balance Sheet" if root_type == "Liability" else "Profit and Loss",
            }
        )
        parent_doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        frappe.log_error(
            f"Error creating parent account {account_name_with_abbr}: {str(e)}",
            "Payroll Indonesia Setup",
        )


def create_default_accounts(company_name: str, company_abbr: str) -> None:
    """
    Create default GL accounts for payroll processing for the specified company.
    """
    json_file_path = frappe.get_app_path("payroll_indonesia", "setup", "default_gl_accounts.json")
    if not os.path.exists(json_file_path):
        frappe.log_error(f"File not found: {json_file_path}", "Payroll Indonesia Setup")
        return

    with open(json_file_path, "r") as f:
        gl_accounts = json.load(f)

    parent_account_options = {
        "expense": [
            "Direct Expenses",
            "Pengeluaran Langsung",
            "Expenses",
            "Biaya",
        ],
        "liability": [
            "Payables",
            "Utang Usaha",
            "Current Liabilities",
            "Kewajiban Lancar",
            "Liabilities",
        ],
        "tax": ["Duties and Taxes", "Utang Pajak"],
    }

    for account in gl_accounts:
        account_name = account.get("account_name")
        root_type = account.get("root_type")
        account_type = account.get("account_type")
        is_group = account.get("is_group", 0)
        account_name_with_abbr = f"{account_name} - {company_abbr}"

        if account_name == "PPh 21 Payable":
            ensure_parent_account("Duties and Taxes", company_name, company_abbr, "Liability")
        elif root_type == "Expense":
            ensure_parent_account("Expenses", company_name, company_abbr, "Expense")
        elif root_type == "Liability" and account_type == "Payable":
            ensure_parent_account("Liabilities", company_name, company_abbr, "Liability")

        if frappe.db.exists("Account", account_name_with_abbr):
            continue

        parent_account = None

        if account_name == "PPh 21 Payable":
            parent_account = get_parent_account(parent_account_options["tax"], company_abbr)
        elif root_type == "Expense":
            parent_account = get_parent_account(parent_account_options["expense"], company_abbr)
        elif root_type == "Liability" and account_type == "Payable":
            parent_account = get_parent_account(parent_account_options["liability"], company_abbr)

        if not parent_account:
            available = frappe.get_all(
                "Account",
                filters={
                    "company": company_name,
                    "root_type": root_type,
                    "is_group": 1,
                },
                pluck="name",
            )
            if available:
                parent_account = available[0]

        if not parent_account:
            warning = (
                f"Skipping account {account_name_with_abbr}: " "No suitable parent account found"
            )
            frappe.logger().warning(warning)
            continue

        try:
            new_account = frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": account_name,
                    "parent_account": parent_account,
                    "company": company_name,
                    "root_type": root_type,
                    "account_type": account_type,
                    "is_group": is_group,
                    "report_type": (
                        "Balance Sheet" if root_type == "Liability" else "Profit and Loss"
                    ),
                }
            )

            new_account.insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.msgprint(f"Created account: {account_name_with_abbr}")

        except Exception as e:
            frappe.log_error(
                f"Error creating account {account_name_with_abbr}: {str(e)}",
                "Payroll Indonesia Setup",
            )


def create_salary_structure_for_company(company_name: str) -> None:
    """
    Create Salary Structure for Indonesian Payroll Standard for the company if not exists.
    The structure and components are loaded from salary_structure.json fixture file.
    """
    json_file_path = frappe.get_app_path("payroll_indonesia", "setup", "salary_structure.json")
    if not os.path.exists(json_file_path):
        frappe.log_error(f"File not found: {json_file_path}", "Payroll Indonesia Setup")
        return

    with open(json_file_path, "r") as f:
        salary_structures = json.load(f)

    for structure in salary_structures:
        structure_name = structure.get(
            "salary_structure_name", structure.get("name", "Indonesian Payroll Standard")
        )
        # Avoid duplicate per company
        exists = frappe.db.exists(
            "Salary Structure", {"salary_structure_name": structure_name, "company": company_name}
        )
        if exists:
            continue
        # Build doc, inject company
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
            frappe.msgprint(f"Created Salary Structure: {structure_name} for {company_name}")
        except Exception as e:
            frappe.log_error(
                f"Error creating Salary Structure for {company_name}: {str(e)}",
                "Payroll Indonesia Setup",
            )


def after_sync() -> None:
    """
    Setup function that runs after app sync.
    Creates default GL accounts for all companies, maps them to salary components,
    migrates Payroll Indonesia Settings tables from default JSON if not present,
    and creates Salary Structure for each company.
    """
    try:
        # Step 1: Ensure fixtures are loaded (handled by Frappe before after_sync)

        # Step 2: Get all companies
        companies = frappe.get_all("Company", fields=["name", "abbr"])

        for company in companies:
            # Step 3: Create default accounts for company
            create_default_accounts(company.name, company.abbr)

            # Step 4: Map GL accounts to salary components
            try:
                assign_gl_accounts_to_salary_components(company.name, company.abbr)
                frappe.logger().info(
                    f"Mapped salary components to GL accounts for company: {company.name}"
                )
            except Exception as e:
                frappe.log_error(
                    f"Error mapping salary components to GL accounts for company {company.name}: {str(e)}",
                    "Payroll Indonesia Setup",
                )

            # Step 5: Create Salary Structure for company
            try:
                create_salary_structure_for_company(company.name)
            except Exception as e:
                frappe.log_error(
                    f"Error creating Salary Structure for company {company.name}: {str(e)}",
                    "Payroll Indonesia Setup",
                )

        # Step 6: Migrate Payroll Indonesia Settings tables if needed
        try:
            setup_default_settings()
            frappe.logger().info("Payroll Indonesia Settings tables migrated (PTKP/TER/Brackets)")
        except Exception as e:
            frappe.log_error(
                f"Error in Payroll Indonesia Settings migration: {str(e)}",
                "Payroll Indonesia Setup",
            )

        frappe.msgprint(
            "Payroll Indonesia: Default GL accounts setup, salary structure, mapping, and settings migration completed"
        )

    except Exception as e:
        frappe.log_error(f"Error in Payroll Indonesia setup: {str(e)}", "Payroll Indonesia Setup")
