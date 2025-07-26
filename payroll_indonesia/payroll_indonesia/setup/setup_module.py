"""Setup utilities for Payroll Indonesia."""

import json
import os
import traceback

import frappe
from .gl_account_mapper import assign_gl_accounts_to_salary_components_all
from .settings_migration import setup_default_settings

__all__ = ["after_sync"]


def ensure_parent(name: str, company: str, root_type: str, report_type: str) -> bool:
    """Create parent account if missing."""
    if frappe.db.exists("Account", {"account_name": name, "company": company}):
        return True

    try:
        doc = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": name,
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
    """Create GL accounts for every company from JSON template."""
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
                parent_name = parent.rsplit(" - ", 1)[0]
                if not ensure_parent(
                    parent_name, company, acc.get("root_type"), acc.get("report_type")
                ):
                    frappe.logger().info(
                        f"Skipped account {acc.get('account_name')} for {company} because parent {parent_name} is missing"
                    )
                    continue
            try:
                doc = frappe.get_doc({"doctype": "Account", **acc})
                doc.insert(ignore_if_duplicate=True, ignore_permissions=True)
                frappe.logger().info(f"Created account {doc.name} for {company}")
            except Exception:
                frappe.logger().error(
                    f"Skipped account {acc.get('account_name')} for {company}\n{traceback.format_exc()}"
                )
        frappe.db.commit()


def after_sync() -> None:
    """Entry point executed on migrate and sync."""
    frappe.logger().info("🚀 Payroll GL Setup started")
    try:
        create_accounts_from_json()
        frappe.db.commit()
    except Exception:
        frappe.logger().error(
            f"Error creating GL accounts\n{traceback.format_exc()}"
        )
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

    try:
        setup_default_settings()
        frappe.db.commit()
    except Exception:
        frappe.logger().error(
            f"Error setting up default Payroll Indonesia settings\n{traceback.format_exc()}"
        )
        frappe.db.rollback()
