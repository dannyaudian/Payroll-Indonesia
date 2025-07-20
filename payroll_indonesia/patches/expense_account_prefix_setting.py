import json
import frappe
from payroll_indonesia.setup.settings_migration import _load_defaults

def execute():
    if not frappe.db.table_exists("Payroll Indonesia Settings"):
        return
    if not frappe.db.exists("Payroll Indonesia Settings", "Payroll Indonesia Settings"):
        return
    settings = frappe.get_single("Payroll Indonesia Settings")
    defaults = _load_defaults()
    prefix = defaults.get("settings", {}).get("expense_account_prefix", "Beban, Expense")
    if not settings.get("expense_account_prefix"):
        settings.expense_account_prefix = prefix
        settings.flags.ignore_permissions = True
        settings.flags.ignore_validate = True
        settings.save()
