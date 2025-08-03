import sys
import types
import importlib
import json
import datetime


def test_december_summary_fallback(monkeypatch):
    frappe = types.SimpleNamespace()

    class DummyLogger:
        def info(self, *a, **k):
            pass

        def warning(self, *a, **k):
            pass

        def error(self, *a, **k):
            pass

    frappe.logger = lambda *a, **k: DummyLogger()
    frappe.log_error = lambda *a, **k: None
    frappe.utils = types.SimpleNamespace(
        getdate=lambda d: datetime.datetime.strptime(d, "%Y-%m-%d"),
        cint=int,
        flt=float,
    )

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = frappe.utils

    if "payroll_indonesia.utils.sync_annual_payroll_history" in sys.modules:
        del sys.modules["payroll_indonesia.utils.sync_annual_payroll_history"]
    sync_mod = importlib.import_module(
        "payroll_indonesia.utils.sync_annual_payroll_history"
    )

    calls = []

    def stub_sync_annual_payroll_history(*, employee, fiscal_year, monthly_results=None, summary=None, **kwargs):
        calls.append(summary)

    monkeypatch.setattr(
        sync_mod, "sync_annual_payroll_history", stub_sync_annual_payroll_history
    )

    # Case 1: tax_type comes from _tax_type in pph21_info
    slip1_info = {
        "_tax_type": "DECEMBER",
        "bruto_total": 1,
        "netto_total": 2,
        "pengurang_netto_total": 3,
        "biaya_jabatan_total": 4,
        "ptkp_annual": 5,
        "pkp_annual": 6,
        "pph21_annual": 7,
        "koreksi_pph21": 8,
    }
    slip1 = types.SimpleNamespace(
        name="SS1",
        employee="EMP1",
        docstatus=1,
        start_date="2024-12-01",
        pph21_info=json.dumps(slip1_info),
        gross_pay=0,
        net_pay=0,
        tax=0,
        tax_type=None,
    )
    sync_mod.sync_salary_slip_to_annual(slip1)
    assert calls[-1] == {
        "bruto_total": 1,
        "netto_total": 2,
        "pengurang_netto_total": 3,
        "biaya_jabatan_total": 4,
        "ptkp_annual": 5,
        "pkp_annual": 6,
        "pph21_annual": 7,
        "koreksi_pph21": 8,
    }

    # Case 2: tax_type inferred from start_date month
    slip2_info = {
        "bruto_total": 10,
        "netto_total": 20,
        "pengurang_netto_total": 30,
        "biaya_jabatan_total": 40,
        "ptkp_annual": 50,
        "pkp_annual": 60,
        "pph21_annual": 70,
        "koreksi_pph21": 80,
    }
    slip2 = types.SimpleNamespace(
        name="SS2",
        employee="EMP1",
        docstatus=1,
        start_date="2024-12-01",
        pph21_info=json.dumps(slip2_info),
        gross_pay=0,
        net_pay=0,
        tax=0,
        tax_type=None,
    )
    sync_mod.sync_salary_slip_to_annual(slip2)
    assert calls[-1] == {
        "bruto_total": 10,
        "netto_total": 20,
        "pengurang_netto_total": 30,
        "biaya_jabatan_total": 40,
        "ptkp_annual": 50,
        "pkp_annual": 60,
        "pph21_annual": 70,
        "koreksi_pph21": 80,
    }
