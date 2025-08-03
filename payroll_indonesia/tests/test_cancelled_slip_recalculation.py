import os
import sys
import types
import importlib
import json


def test_cancelled_slip_recalculates_summary(monkeypatch):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

    frappe = types.SimpleNamespace()

    class DummyLogger:
        def info(self, msg, *args):
            pass

        def warning(self, msg, *args):
            pass

        def debug(self, msg, *args):
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
        def __init__(self, salary_slip, bruto, pengurang_netto, biaya_jabatan, pph21):
            self.salary_slip = salary_slip
            self.bruto = bruto
            self.pengurang_netto = pengurang_netto
            self.biaya_jabatan = biaya_jabatan
            self.pph21 = pph21

    class HistoryDoc:
        def __init__(self):
            self.name = "APH-1"
            self.flags = types.SimpleNamespace()
            self.saved = False
            self.docstatus = 1
            self.monthly_details = [
                Detail("SS-1", 100, 10, 5, 2),
                Detail("SS-2", 200, 20, 10, 4),
            ]
            self.bruto_total = 300
            self.pengurang_netto_total = 30
            self.biaya_jabatan_total = 15
            self.netto_total = 255
            self.pph21_annual = 0
            self.koreksi_pph21 = 0

        def is_new(self):
            return False

        def get(self, key, default=None):
            return getattr(self, key, default)

        def set(self, key, value):
            setattr(self, key, value)

        def save(self):
            self.saved = True

    history = HistoryDoc()
    monkeypatch.setattr(
        sync_mod, "get_or_create_annual_payroll_history", lambda *a, **k: history
    )

    result = sync_mod.sync_annual_payroll_history_for_bulan(
        employee={"name": "EMP1"},
        fiscal_year="2024",
        cancelled_salary_slip="SS-2",
    )

    assert result == "APH-1"
    assert history.saved
    assert len(history.monthly_details) == 1
    assert history.bruto_total == 100
    assert history.pengurang_netto_total == 10
    assert history.biaya_jabatan_total == 5
    assert history.netto_total == 85
    assert history.pph21_annual == 2
    assert history.koreksi_pph21 == 0
