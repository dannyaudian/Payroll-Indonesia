import sys
import os
import types
import importlib
import datetime


def test_sync_to_annual_payroll_history_sets_numeric_month(monkeypatch):
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

    def logger():
        return DummyLogger()

    def flt(val, precision=None):
        return float(val)

    def getdate(val):
        return datetime.datetime.strptime(val, "%Y-%m-%d")

    def safe_eval(expr, context=None):
        return eval(expr, context or {})

    frappe.logger = logger
    frappe.get_doc = lambda *args, **kwargs: {}
    frappe.throw = lambda *args, **kwargs: None
    frappe.utils = utils_mod
    utils_mod.flt = flt
    utils_mod.getdate = getdate
    safe_exec_mod.safe_eval = safe_eval

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils_mod
    sys.modules["frappe.utils.safe_exec"] = safe_exec_mod

    salary_slip_mod = importlib.import_module("payroll_indonesia.override.salary_slip")
    sync_mod = importlib.import_module("payroll_indonesia.utils.sync_annual_payroll_history")
    CustomSalarySlip = salary_slip_mod.CustomSalarySlip

    captured = []

    def fake_sync(**kwargs):
        captured.extend(kwargs.get("monthly_results", []))

    monkeypatch.setattr(sync_mod, "sync_annual_payroll_history", fake_sync)

    result = {
        "bruto": 0,
        "pengurang_netto": 0,
        "biaya_jabatan": 0,
        "netto": 0,
        "pkp": 0,
        "rate": "",
        "pph21": 0,
    }

    ss = CustomSalarySlip()
    ss.employee = {"name": "EMP-001"}
    ss.name = "SS-1"
    ss.fiscal_year = "2024"
    ss.start_date = "2024-05-10"
    ss.sync_to_annual_payroll_history(result, mode="monthly")

    ss2 = CustomSalarySlip()
    ss2.employee = {"name": "EMP-001"}
    ss2.name = "SS-2"
    ss2.fiscal_year = "2024"
    ss2.month = "March"
    ss2.sync_to_annual_payroll_history(result, mode="monthly")

    assert captured[0]["bulan"] == 5
    assert captured[1]["bulan"] == 3

    for mod in [
        "frappe",
        "frappe.utils",
        "frappe.utils.safe_exec",
        "payroll_indonesia.override.salary_slip",
        "payroll_indonesia.utils.sync_annual_payroll_history",
    ]:
        sys.modules.pop(mod, None)

