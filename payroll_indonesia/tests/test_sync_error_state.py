import os
import sys
import types
import importlib
import json


def test_sync_error_state_forces_save(monkeypatch):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

    frappe = types.SimpleNamespace()

    class DummyLogger:
        def info(self, msg):
            pass

        def warning(self, msg):
            pass

        def debug(self, msg):
            pass

    frappe.logger = lambda *a, **k: DummyLogger()
    frappe.throw = lambda *a, **k: None
    frappe.log_error = lambda *a, **k: None
    frappe.db = types.SimpleNamespace(savepoint=lambda name: None, rollback=lambda save_point=None: None)
    frappe.utils = types.SimpleNamespace(now=lambda: "now")
    frappe.as_json = json.dumps
    frappe.session = types.SimpleNamespace(user="tester")

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = frappe.utils

    if "payroll_indonesia.utils.sync_annual_payroll_history" in sys.modules:
        del sys.modules["payroll_indonesia.utils.sync_annual_payroll_history"]
    sync_mod = importlib.import_module("payroll_indonesia.utils.sync_annual_payroll_history")

    class HistoryDoc:
        def __init__(self):
            self.name = "APH-1"
            self.flags = types.SimpleNamespace()
            self.saved = False

        def is_new(self):
            return False

        def get(self, key, default=None):
            return getattr(self, key, default)

        def set(self, key, value):
            setattr(self, key, value)

        def save(self):
            self.saved = True

    doc = HistoryDoc()
    monkeypatch.setattr(sync_mod, "get_or_create_annual_payroll_history", lambda *a, **k: doc)

    result = sync_mod.sync_annual_payroll_history(
        employee={"name": "EMP1"},
        fiscal_year="2024",
        error_state={"detail": "failure"},
    )

    assert result == "APH-1"
    assert doc.saved
    assert doc.error_state == json.dumps({"detail": "failure"})


def test_cancelled_slip_sets_error_state_and_preserves_row(monkeypatch):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

    frappe = types.SimpleNamespace()

    class DummyLogger:
        def info(self, msg):
            pass

        def warning(self, msg):
            pass

        def debug(self, msg):
            pass

    frappe.logger = lambda *a, **k: DummyLogger()
    frappe.throw = lambda *a, **k: None
    frappe.log_error = lambda *a, **k: None
    frappe.db = types.SimpleNamespace(
        savepoint=lambda name: None,
        rollback=lambda save_point=None: None,
        exists=lambda dt, name: True,
    )
    frappe.utils = types.SimpleNamespace(now=lambda: "now")
    frappe.as_json = json.dumps
    frappe.session = types.SimpleNamespace(user="tester")

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = frappe.utils

    if "payroll_indonesia.utils.sync_annual_payroll_history" in sys.modules:
        del sys.modules["payroll_indonesia.utils.sync_annual_payroll_history"]
    sync_mod = importlib.import_module("payroll_indonesia.utils.sync_annual_payroll_history")

    class Detail:
        def __init__(self):
            self.salary_slip = "SS-FAIL"
            self.error_state = None

    class HistoryDoc:
        def __init__(self):
            self.name = "APH-1"
            self.flags = types.SimpleNamespace()
            self.saved = False
            self.monthly_details = [Detail()]

        def is_new(self):
            return False

        def get(self, key, default=None):
            return getattr(self, key, default)

        def set(self, key, value):
            setattr(self, key, value)

        def save(self):
            self.saved = True

    doc = HistoryDoc()
    monkeypatch.setattr(sync_mod, "get_or_create_annual_payroll_history", lambda *a, **k: doc)

    result = sync_mod.sync_annual_payroll_history(
        employee={"name": "EMP1"},
        fiscal_year="2024",
        cancelled_salary_slip="SS-FAIL",
        error_state={"reason": "failed"},
    )

    assert result == "APH-1"
    assert doc.saved
    assert len(doc.monthly_details) == 1
    assert doc.monthly_details[0].error_state == json.dumps({"reason": "failed"})
    assert doc.error_state == json.dumps({"reason": "failed"})

