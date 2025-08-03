import sys
import types
import importlib
import json


def test_wrapper_normalizes_and_logs(monkeypatch):
    # Stub frappe environment
    frappe = types.SimpleNamespace()

    class DummyLogger:
        def __init__(self):
            self.debug_messages = []

        def debug(self, msg, *args):
            self.debug_messages.append(msg % args if args else msg)

        def info(self, msg, *args):
            pass

        def warning(self, msg, *args):
            pass

    logger = DummyLogger()
    frappe.logger = lambda *a, **k: logger
    frappe.throw = lambda *a, **k: None
    frappe.log_error = lambda *a, **k: None
    frappe.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
    frappe.utils = types.SimpleNamespace(now=lambda: "now")
    frappe.as_json = json.dumps
    frappe.session = types.SimpleNamespace(user="tester")

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = frappe.utils

    if "payroll_indonesia.utils.sync_annual_payroll_history" in sys.modules:
        del sys.modules["payroll_indonesia.utils.sync_annual_payroll_history"]
    sync_mod = importlib.import_module(
        "payroll_indonesia.utils.sync_annual_payroll_history"
    )

    calls = []

    def stub_sync_for_bulan(
        *,
        employee,
        fiscal_year,
        bulan,
        monthly_results=None,
        summary=None,
        cancelled_salary_slip=None,
        error_state=None,
    ):
        calls.append(
            {
                "employee": employee,
                "bulan": bulan,
                "summary": summary,
                "error_state": error_state,
            }
        )
        return "APH-1"

    monkeypatch.setattr(
        sync_mod, "sync_annual_payroll_history_for_bulan", stub_sync_for_bulan
    )

    result = sync_mod.sync_annual_payroll_history(
        employee="EMP1",
        fiscal_year="2024",
        monthly_results=[{"bulan": 1}, {"bulan": 2}],
        summary={"total": 100},
        error_state={"msg": "err"},
    )

    assert result == "APH-1"
    assert len(logger.debug_messages) == 2
    assert calls[0]["summary"] is None
    assert calls[0]["error_state"] is None
    assert calls[1]["summary"] == {"total": 100}
    assert calls[1]["error_state"] == {"msg": "err"}
    assert calls[1]["employee"] == {
        "name": "EMP1",
        "company": None,
        "employee_name": None,
    }
