import os
import sys
import types
import importlib
import json


def test_calculate_pph21_december_allows_negative(monkeypatch):
    frappe = types.SimpleNamespace()

    class DummyLogger:
        def debug(self, *a, **k):
            pass
        def warning(self, *a, **k):
            pass

    frappe.logger = lambda *a, **k: DummyLogger()
    frappe.throw = lambda *a, **k: None
    frappe.ValidationError = type("ValidationError", (Exception,), {})
    frappe.db = types.SimpleNamespace(exists=lambda *a, **k: False)
    sys.modules["frappe"] = frappe

    module = importlib.import_module("payroll_indonesia.config.pph21_ter_december")
    monkeypatch.setattr(module, "get_ptkp_amount", lambda emp: 0)
    monkeypatch.setattr(module, "calculate_pph21_progressive", lambda pkp: 0)

    result = module.calculate_pph21_december(
        taxable_income=0,
        employee={"employment_type": "Full-time"},
        company="CMP",
        ytd_income=0,
        ytd_tax_paid=100,
    )
    assert result["koreksi_pph21"] == -100
    assert result["pph21_bulan"] == -100


def test_salary_slip_negative_pph21_updates_deduction(monkeypatch):
    frappe = types.ModuleType("frappe")
    utils_mod = types.ModuleType("frappe.utils")
    safe_exec_mod = types.ModuleType("frappe.utils.safe_exec")

    class DummyLogger:
        def info(self, *a, **k):
            pass
        def warning(self, *a, **k):
            pass
        def debug(self, *a, **k):
            pass

    frappe.logger = lambda *a, **k: DummyLogger()
    frappe.throw = lambda *a, **k: None
    frappe.ValidationError = type("ValidationError", (Exception,), {})
    frappe.get_doc = lambda *a, **k: {}
    frappe.log_error = lambda *a, **k: None
    utils_mod.flt = lambda v, precision=None: float(v)
    utils_mod.file_lock = lambda *a, **k: None
    safe_exec_mod.safe_eval = lambda expr, context=None: eval(expr, context or {})
    frappe.utils = utils_mod
    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils_mod
    sys.modules["frappe.utils.safe_exec"] = safe_exec_mod

    salary_slip_mod = importlib.import_module("payroll_indonesia.override.salary_slip")
    CustomSalarySlip = salary_slip_mod.CustomSalarySlip

    monkeypatch.setattr(
        salary_slip_mod,
        "calculate_pph21_december",
        lambda taxable_income, employee, company, ytd_income, ytd_tax_paid: {
            "pph21_bulan": -20,
            "koreksi_pph21": -20,
        },
    )

    monkeypatch.setattr(
        CustomSalarySlip,
        "_get_ytd_income_and_tax",
        lambda self: (0, 0),
        raising=False,
    )

    captured = {}
    monkeypatch.setattr(
        CustomSalarySlip,
        "update_pph21_row",
        lambda self, amt: captured.setdefault("amount", amt),
        raising=False,
    )

    ss = CustomSalarySlip()
    ss.employee = {"employment_type": "Full-time"}
    ss.company = "CMP"
    ss.start_date = "2024-12-01"
    ss.earnings = []
    ss.deductions = []

    amt = ss.calculate_income_tax_december()
    assert amt == -20
    assert captured["amount"] == -20
    assert ss.tax == -20
