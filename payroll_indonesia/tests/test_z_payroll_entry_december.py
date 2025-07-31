import sys
import os
import types
import json
import importlib


def test_create_slip_in_december_mode(monkeypatch):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

    # --- Frappe stubs -----------------------------------------------------
    frappe = types.ModuleType("frappe")
    utils_mod = types.ModuleType("frappe.utils")
    safe_exec_mod = types.ModuleType("frappe.utils.safe_exec")

    def flt(val, precision=None):
        return float(val)

    def safe_eval(expr, context=None):
        return eval(expr, context or {})

    class DummyLogger:
        def info(self, msg):
            pass

        def warning(self, msg):
            pass

    def logger():
        return DummyLogger()

    frappe.utils = utils_mod
    frappe.logger = logger
    frappe.get_doc = lambda *args, **kwargs: {}
    frappe.get_cached_doc = frappe.get_doc
    frappe.ValidationError = type("ValidationError", (Exception,), {})
    utils_mod.flt = flt
    utils_mod.safe_exec = safe_exec_mod
    safe_exec_mod.safe_eval = safe_eval

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils_mod
    sys.modules["frappe.utils.safe_exec"] = safe_exec_mod

    # Import modules after stubbing frappe
    payroll_entry = importlib.import_module("payroll_indonesia.override.payroll_entry")
    salary_slip_module = importlib.import_module("payroll_indonesia.override.salary_slip")
    CustomSalarySlip = salary_slip_module.CustomSalarySlip
    pph21_ter_december = importlib.import_module("payroll_indonesia.config.pph21_ter_december")

    # --- Monkeypatch helpers ---------------------------------------------
    def fake_calc_pph21_december(employee_doc, slips, pph21_paid_jan_nov=0):
        return {"pph21_month": 1500, "pph21_annual": 18000, "pkp_annual": 100000}

    def db_set(self, field, value):
        setattr(self, field, value)

    def save(self, ignore_permissions=True):
        self.saved = True
        return self

    def append(self, table_field, row):
        getattr(self, table_field).append(row)

    def sync_to_annual_payroll_history(self, result, mode="monthly"):
        pass

    def _init(self, **data):
        for k, v in data.items():
            setattr(self, k, v)
        if not hasattr(self, "gross_pay"):
            self.gross_pay = 0

    monkeypatch.setattr(pph21_ter_december, "calculate_pph21_TER_december", fake_calc_pph21_december)
    monkeypatch.setattr(CustomSalarySlip, "db_set", db_set, raising=False)
    monkeypatch.setattr(CustomSalarySlip, "save", save, raising=False)
    monkeypatch.setattr(CustomSalarySlip, "append", append, raising=False)
    monkeypatch.setattr(
        CustomSalarySlip,
        "sync_to_annual_payroll_history",
        sync_to_annual_payroll_history,
        raising=False,
    )
    monkeypatch.setattr(CustomSalarySlip, "__init__", _init, raising=False)

    class DummyBase:
        def create_salary_slips(self):
            slip = {
                "employee": {"employment_type": "Full-time", "tax_status": "TK/0"},
                "earnings": [
                    {
                        "amount": 1000,
                        "is_tax_applicable": 1,
                        "do_not_include_in_total": 0,
                        "statistical_component": 0,
                        "exempted_from_income_tax": 0,
                    }
                ],
                "deductions": [
                    {
                        "salary_component": "BPJS",
                        "amount": 100,
                        "is_income_tax_component": 1,
                        "do_not_include_in_total": 0,
                        "statistical_component": 0,
                    }
                ],
            }
            return [slip]

    class TestPayrollEntry(payroll_entry.CustomPayrollEntry, DummyBase):
        pass

    entry = TestPayrollEntry()
    entry.run_payroll_indonesia_december = True

    slips = entry.create_salary_slips()

    assert slips, "Expected one slip to be generated"
    slip = slips[0]
    assert slip["tax_type"] == "DECEMBER"
    info = json.loads(slip["pph21_info"])
    assert "pkp_annual" in info and "pph21_month" in info

    # Cleanup so other tests can import fresh modules
    for mod in [
        "frappe",
        "frappe.utils",
        "frappe.utils.safe_exec",
        "payroll_indonesia.override.payroll_entry",
        "payroll_indonesia.override.salary_slip",
        "payroll_indonesia.config.pph21_ter_december",
        "payroll_indonesia.config.pph21_ter",
    ]:
        sys.modules.pop(mod, None)
