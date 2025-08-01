import sys
import os
import types
import importlib


def test_eval_formula_with_allowances(monkeypatch):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    frappe = types.ModuleType("frappe")
    utils_mod = types.ModuleType("frappe.utils")
    safe_exec_mod = types.ModuleType("frappe.utils.safe_exec")

    frappe.get_hooks = lambda *args, **kwargs: {}
    frappe.get_attr = lambda path: None
    frappe.log_error = lambda *args, **kwargs: None
    utils_mod.safe_exec = safe_exec_mod
    utils_mod.flt = lambda val, precision=None: float(val)
    safe_exec_mod.safe_eval = lambda expr, context=None: eval(expr, context or {})
    frappe.utils = utils_mod

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils_mod
    sys.modules["frappe.utils.safe_exec"] = safe_exec_mod

    salary_slip_module = importlib.import_module("payroll_indonesia.override.salary_slip")
    CustomSalarySlip = salary_slip_module.CustomSalarySlip

    struct_row = types.SimpleNamespace(formula="meal_allowance + transport_allowance", condition=None)

    slip = CustomSalarySlip()
    slip.meal_allowance = 50
    slip.transport_allowance = 75
    assert slip.eval_condition_and_formula(struct_row, {}) == 125

    delattr(slip, "meal_allowance")
    delattr(slip, "transport_allowance")
    slip.salary_structure_assignment = types.SimpleNamespace(meal_allowance=100, transport_allowance=120)
    assert slip.eval_condition_and_formula(struct_row, {}) == 220

    for mod in ["frappe", "frappe.utils", "frappe.utils.safe_exec", "payroll_indonesia.override.salary_slip"]:
        sys.modules.pop(mod, None)
