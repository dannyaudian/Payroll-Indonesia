import sys
import os
import types
import importlib
import datetime
import json


def test_salary_slip_validate_submit_sync_once(monkeypatch):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

    frappe = types.ModuleType("frappe")
    utils_mod = types.ModuleType("frappe.utils")
    safe_exec_mod = types.ModuleType("frappe.utils.safe_exec")

    class DummyLogger:
        def info(self, msg):
            pass
        def warning(self, msg):
            pass
        def error(self, msg):
            pass

    frappe.logger = lambda *a, **k: DummyLogger()
    frappe.get_doc = lambda *args, **kwargs: {}
    frappe.throw = lambda *args, **kwargs: None
    frappe.ValidationError = type("ValidationError", (Exception,), {})
    frappe.log_error = lambda *args, **kwargs: None
    utils_mod.flt = lambda val, precision=None: float(val)
    utils_mod.getdate = lambda val: datetime.datetime.strptime(val, "%Y-%m-%d")
    utils_mod.file_lock = lambda *a, **k: None
    safe_exec_mod.safe_eval = lambda expr, context=None: eval(expr, context or {})

    frappe.utils = utils_mod
    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils_mod
    sys.modules["frappe.utils.safe_exec"] = safe_exec_mod

    salary_slip_mod = importlib.import_module("payroll_indonesia.override.salary_slip")
    CustomSalarySlip = salary_slip_mod.CustomSalarySlip

    calls = []

    def fake_sync(**kwargs):
        calls.extend(kwargs.get("monthly_results", []))
        return "APH-001"

    monkeypatch.setattr(salary_slip_mod, "sync_annual_payroll_history", fake_sync)
    monkeypatch.setattr(CustomSalarySlip, "update_pph21_row", lambda self, amt: None, raising=False)

    def fake_calc(self):
        result = {
            "bruto": 0,
            "pengurang_netto": 0,
            "biaya_jabatan": 0,
            "netto": 0,
            "pkp": 0,
            "rate": 0,
            "pph21": 0,
        }
        self.pph21_info = json.dumps(result)
        return 0

    monkeypatch.setattr(CustomSalarySlip, "calculate_income_tax", fake_calc, raising=False)

    ss = CustomSalarySlip()
    ss.employee = {"name": "EMP-001"}
    ss.name = "SS-1"
    ss.fiscal_year = "2024"
    ss.start_date = "2024-05-10"

    ss.validate()
    ss.on_submit()

    assert len(calls) == 1
    assert ss._annual_history_synced


def test_salary_slip_on_submit_populates_monthly_detail(monkeypatch):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

    frappe = types.ModuleType("frappe")
    utils_mod = types.ModuleType("frappe.utils")
    safe_exec_mod = types.ModuleType("frappe.utils.safe_exec")

    class DummyLogger:
        def info(self, msg):
            pass
        def warning(self, msg):
            pass
        def error(self, msg):
            pass

    frappe.logger = lambda *a, **k: DummyLogger()
    frappe.get_doc = lambda *args, **kwargs: {}
    frappe.throw = lambda *args, **kwargs: None
    frappe.ValidationError = type("ValidationError", (Exception,), {})
    frappe.log_error = lambda *args, **kwargs: None
    utils_mod.flt = lambda val, precision=None: float(val)
    utils_mod.getdate = lambda val: datetime.datetime.strptime(val, "%Y-%m-%d")
    utils_mod.file_lock = lambda *a, **k: None
    safe_exec_mod.safe_eval = lambda expr, context=None: eval(expr, context or {})

    frappe.utils = utils_mod
    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils_mod
    sys.modules["frappe.utils.safe_exec"] = safe_exec_mod

    salary_slip_mod = importlib.import_module("payroll_indonesia.override.salary_slip")
    CustomSalarySlip = salary_slip_mod.CustomSalarySlip

    captured = {}

    def fake_sync(**kwargs):
        captured.update(kwargs)
        return "APH-002"

    monkeypatch.setattr(salary_slip_mod, "sync_annual_payroll_history", fake_sync)
    monkeypatch.setattr(CustomSalarySlip, "update_pph21_row", lambda self, amt: None, raising=False)

    ss = CustomSalarySlip()
    ss.employee = {"name": "EMP-002"}
    ss.name = "SS-2"
    ss.fiscal_year = "2024"
    ss.start_date = "2024-06-01"
    ss.pph21_info = json.dumps({
        "bruto": 100,
        "pengurang_netto": 10,
        "biaya_jabatan": 5,
        "netto": 85,
        "pkp": 0,
        "rate": 5,
        "pph21": 8,
    })

    ss.on_submit()

    monthly = captured.get("monthly_results", [])[0]
    assert monthly["bulan"] == 6
    assert monthly["salary_slip"] == "SS-2"
    assert monthly["pph21"] == 8
