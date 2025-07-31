import sys
import os
import types
import importlib


def test_get_salary_slips(monkeypatch):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

    # --- Frappe stubs -----------------------------------------------------
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

    def safe_eval(expr, context=None):
        return eval(expr, context or {})

    # get_all will be used by get_salary_slips
    def get_all(doctype, filters=None, pluck=None):
        assert doctype == "Salary Slip"
        assert filters == {"payroll_entry": "PE-0001"}
        assert pluck == "name"
        return ["SS1", "SS2"]

    frappe.get_all = get_all
    frappe.get_doc = lambda *args, **kwargs: {}
    frappe.get_cached_doc = frappe.get_doc
    frappe.throw = lambda *args, **kwargs: None
    frappe.utils = utils_mod
    frappe.logger = logger
    utils_mod.flt = flt
    utils_mod.safe_exec = safe_exec_mod
    safe_exec_mod.safe_eval = safe_eval

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils_mod
    sys.modules["frappe.utils.safe_exec"] = safe_exec_mod

    payroll_entry = importlib.import_module("payroll_indonesia.override.payroll_entry")
    CustomPayrollEntry = payroll_entry.CustomPayrollEntry

    entry = CustomPayrollEntry()
    entry.name = "PE-0001"

    slips = entry.get_salary_slips()
    assert slips == ["SS1", "SS2"]

    # Cleanup modules so other tests import fresh versions
    for mod in [
        "frappe",
        "frappe.utils",
        "frappe.utils.safe_exec",
        "payroll_indonesia.override.payroll_entry",
        "payroll_indonesia.override.salary_slip",
    ]:
        sys.modules.pop(mod, None)

