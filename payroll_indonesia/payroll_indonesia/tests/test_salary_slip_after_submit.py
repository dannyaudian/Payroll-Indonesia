import sys
import types
import pytest

pytest.importorskip("frappe")


def test_after_submit_updates_tax_summary(monkeypatch):
    frappe = types.ModuleType("frappe")
    frappe.utils = types.ModuleType("frappe.utils")
    frappe.utils.flt = float
    frappe.utils.cint = int
    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = frappe.utils

    import importlib
    ssf = importlib.import_module("payroll_indonesia.override.salary_slip_functions")

    called = {}
    monkeypatch.setattr(ssf, "utils", types.SimpleNamespace(update_employee_tax_summary=lambda emp, slip: called.setdefault("args", (emp, slip))))
    monkeypatch.setattr(ssf, "logger", types.SimpleNamespace(debug=lambda *a, **k: None, exception=lambda *a, **k: None))

    doc = types.SimpleNamespace(employee="EMP-1", name="SS-001", calculate_indonesia_tax=1, flags=types.SimpleNamespace())

    ssf.after_submit(doc)

    assert called.get("args") == ("EMP-1", "SS-001")
