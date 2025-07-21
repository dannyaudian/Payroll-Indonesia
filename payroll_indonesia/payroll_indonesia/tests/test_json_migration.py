import importlib
import json
import sys
import types


def setup_frappe(settings):
    frappe = types.ModuleType("frappe")
    frappe.utils = types.ModuleType("frappe.utils")
    frappe.utils.cint = int
    frappe.utils.flt = float
    frappe.utils.now = lambda: None
    frappe.utils.get_site_path = lambda *a, **k: ""
    frappe._ = lambda x: x
    frappe.msgprint = lambda *a, **k: None
    frappe.whitelist = lambda *a, **k: (lambda f: f)
    frappe.get_single = lambda name: settings
    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = frappe.utils

    model = types.ModuleType("frappe.model")
    document = types.ModuleType("frappe.model.document")
    document.Document = object
    sys.modules["frappe.model"] = model
    sys.modules["frappe.model.document"] = document

    return frappe


def test_migrate_json_to_child_table(monkeypatch):
    settings = types.SimpleNamespace(
        gl_account_mappings=[],
        expense_accounts_json=json.dumps({"gaji": {"account_name": "Beban Gaji"}}),
        payable_accounts_json=json.dumps({"hutang": {"account_name": "Hutang"}}),
        flags=types.SimpleNamespace(),
    )
    settings.append = lambda table, row: settings.gl_account_mappings.append(row)
    settings.save = lambda ignore_permissions=True: None

    setup_frappe(settings)

    mod = importlib.import_module(
        "payroll_indonesia.payroll_indonesia.doctype.payroll_indonesia_settings.payroll_indonesia_settings"
    )

    count = mod.migrate_json_to_child_table()

    assert count == 2
    assert settings.gl_account_mappings[0]["account_key"] == "gaji"
    assert settings.gl_account_mappings[1]["category"] == "payable_accounts"


def test_migrate_json_skips_when_table_filled(monkeypatch):
    settings = types.SimpleNamespace(
        gl_account_mappings=[{"account_key": "existing"}],
        expense_accounts_json=json.dumps({"gaji": {"account_name": "Beban Gaji"}}),
        payable_accounts_json=json.dumps({"hutang": {"account_name": "Hutang"}}),
        flags=types.SimpleNamespace(),
    )
    settings.append = lambda *a, **k: settings.gl_account_mappings.append({})
    settings.save = lambda ignore_permissions=True: None

    setup_frappe(settings)

    mod = importlib.import_module(
        "payroll_indonesia.payroll_indonesia.doctype.payroll_indonesia_settings.payroll_indonesia_settings"
    )

    count = mod.migrate_json_to_child_table()

    assert count == 0
    assert len(settings.gl_account_mappings) == 1
