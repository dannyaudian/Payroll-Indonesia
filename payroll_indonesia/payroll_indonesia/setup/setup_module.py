"""Setup utilities for Payroll Indonesia."""

import json
import os
import traceback

import frappe

from .gl_account_mapper import assign_gl_accounts_to_salary_components_all
from .settings_migration import setup_default_settings

__all__ = ["after_sync"]


def ensure_parent(name: str, company: str, root_type: str, report_type: str) -> bool:
    """
    Create parent account if missing or update mismatched metadata.
    'name' MUST be in the format "Nama Parent - {company_abbr}".
    """
    if frappe.db.exists("Account", name):
        doc = frappe.get_doc("Account", name)
        updates: dict[str, str] = {}
        if doc.root_type != root_type:
            updates["root_type"] = root_type
        if doc.report_type != report_type:
            updates["report_type"] = report_type
        if updates:
            frappe.logger().warning(f"Updating parent account {name} for {company} with {updates}")
            frappe.db.set_value("Account", name, updates, update_modified=False)
        return True

    try:
        doc = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": name.rsplit(" - ", 1)[0],  # Extract plain name for account_name field
                "name": name,
                "company": company,
                "is_group": 1,
                "root_type": root_type,
                "report_type": report_type,
            }
        )
        doc.insert(ignore_if_duplicate=True, ignore_permissions=True)
        frappe.logger().info(f"Created parent account {doc.name} for {company}")
        return True
    except Exception:
        frappe.logger().error(
            f"Failed creating parent account {name} for {company}\n{traceback.format_exc()}"
        )
        return False


def create_accounts_from_json() -> None:
    """Create GL accounts for every company from JSON template. 
    All parent_account references must be in format 'Nama Parent - {company_abbr}'."""
    path = frappe.get_app_path(
        "payroll_indonesia",
        "setup",
        "default_gl_accounts.json",
    )
    if not os.path.exists(path):
        frappe.logger().error(f"GL account template not found: {path}")
        return

    with open(path) as f:
        template = f.read()

    companies = frappe.get_all("Company", fields=["name", "abbr"])
    for comp in companies:
        company = comp["name"]
        abbr = comp["abbr"]
        try:
            accounts = json.loads(
                frappe.render_template(template, {"company": company, "company_abbr": abbr})
            )
        except Exception:
            frappe.logger().error(
                f"Failed loading GL accounts for {company}\n{traceback.format_exc()}"
            )
            continue

        frappe.logger().info(f"Processing GL accounts for {company}")
        for acc in accounts:
            parent = acc.get("parent_account")
            if parent:
                # Always convert to ERPNext format: "Nama Parent - {abbr}"
                parent_account_full = f"{parent} - {abbr}"
                if not ensure_parent(
                    parent_account_full,
                    company,
                    acc.get("root_type"),
                    acc.get("report_type"),
                ):
                    frappe.logger().info(
                        f"Skipped account {acc.get('account_name')} for {company} because parent {parent_account_full} is missing"
                    )
                    continue
                # Always update the field for insert
                acc["parent_account"] = parent_account_full

            # If the account itself is a group, also ensure its own name follows ERPNext format
            # But account_name field should NOT have abbr, only .name
            # The default_gl_accounts.json should supply proper account_name and name if needed

            try:
                doc = frappe.get_doc({"doctype": "Account", **acc})
                doc.insert(ignore_if_duplicate=True, ignore_permissions=True)
                frappe.logger().info(f"Created account {doc.name} for {company}")
            except Exception:
                frappe.logger().error(
                    f"Skipped account {acc.get('account_name')} for {company}\n{traceback.format_exc()}"
                )
        frappe.db.commit()

def create_salary_structures_from_json():
    """Create Salary Structure from JSON template if not exists."""
    path = frappe.get_app_path(
        "payroll_indonesia",
        "setup",
        "salary_structure.json",
    )
    if not os.path.exists(path):
        frappe.logger().error(f"Salary Structure template not found: {path}")
        return

    with open(path) as f:
        template = f.read()

    try:
        structures = json.loads(template)
    except Exception:
        frappe.logger().error(
            f"Failed loading Salary Structure template\n{traceback.format_exc()}"
        )
        return

    for struct in structures:
        name = struct.get("name") or struct.get("salary_structure_name")
        # Check if already exists (by name)
        if name and frappe.db.exists("Salary Structure", name):
            frappe.logger().info(f"Salary Structure '{name}' already exists, skipping.")
            continue

        try:
            doc = frappe.get_doc({"doctype": "Salary Structure", **struct})
            doc.insert(ignore_if_duplicate=True, ignore_permissions=True)
            frappe.logger().info(f"Created Salary Structure: {doc.name}")
        except Exception:
            frappe.logger().error(
                f"Skipped Salary Structure {name}\n{traceback.format_exc()}"
            )

def after_sync() -> None:
    """Entry point executed on migrate and sync."""
    frappe.logger().info("🚀 Payroll GL Setup started")
    try:
        create_accounts_from_json()
        frappe.db.commit()
    except Exception:
        frappe.logger().error(f"Error creating GL accounts\n{traceback.format_exc()}")
        frappe.db.rollback()
        return

    try:
        assign_gl_accounts_to_salary_components_all()
        frappe.db.commit()
    except Exception:
        frappe.logger().error(
            f"Error assigning GL accounts to salary components\n{traceback.format_exc()}"
        )
        frappe.db.rollback()
        return

    # Tambahkan pemanggilan salary structure di sini
    try:
        create_salary_structures_from_json()
        frappe.db.commit()
    except Exception:
        frappe.logger().error(
            f"Error creating Salary Structures\n{traceback.format_exc()}"
        )
        frappe.db.rollback()
        return

    try:
        setup_default_settings()
    except Exception:
        frappe.logger().error(
            f"Error setting up default Payroll Indonesia settings\n{traceback.format_exc()}"
        )
        frappe.db.rollback()