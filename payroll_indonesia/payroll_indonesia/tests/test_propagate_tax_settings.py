import sys
import types
import importlib


def _setup_frappe():
    frappe = types.ModuleType("frappe")
    frappe.utils = types.ModuleType("frappe.utils")
    frappe.utils.flt = float
    frappe.utils.cint = int
    frappe.utils.getdate = lambda v=None: v
    frappe.utils.add_days = lambda d, n=0: d
    frappe.utils.add_months = lambda d, m=0: d
    frappe.utils.date_diff = lambda a, b: 0
    frappe._ = lambda x: x
    frappe.throw = lambda msg, title=None: (_ for _ in ()).throw(Exception(msg))
    frappe.get_cached_doc = lambda *a, **k: types.SimpleNamespace()
    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = frappe.utils

    model = types.ModuleType("frappe.model")
    document_module = types.ModuleType("frappe.model.document")

    class Document:
        pass

    document_module.Document = Document
    sys.modules["frappe.model"] = model
    sys.modules["frappe.model.document"] = document_module

    # stub salary_slip package to avoid heavy dependencies
    ss_pkg = types.ModuleType("payroll_indonesia.override.salary_slip")
    ss_pkg.IndonesiaPayrollSalarySlip = object
    ss_pkg.calculate_bpjs = lambda *a, **k: None
    ss_pkg.calculate_ytd_and_ytm = lambda *a, **k: None
    sys.modules["payroll_indonesia.override.salary_slip"] = ss_pkg


_def_mod = None


def _load_module():
    global _def_mod
    if _def_mod is None:
        _setup_frappe()
        _def_mod = importlib.import_module("payroll_indonesia.override.payroll_entry")
    return _def_mod


def test_custom_payroll_entry_propagates_settings():
    mod = _load_module()
    CustomPayrollEntry = mod.CustomPayrollEntry

    pe = CustomPayrollEntry()
    pe.calculate_indonesia_tax = 1
    pe.tax_method = "Progressive"
    pe.is_december_override = 1
    pe.ter_method_enabled = 0

    slip = types.SimpleNamespace(calculate_indonesia_tax=0, tax_method=None, is_december_override=0)

    pe.propagate_tax_settings_to_slips([slip])

    assert slip.calculate_indonesia_tax == 1
    assert slip.tax_method == "Progressive"
    assert slip.is_december_override == 1


def test_wrapper_propagates_settings():
    mod = _load_module()
    PayrollEntryIndonesia = mod.PayrollEntryIndonesia

    doc = types.SimpleNamespace(
        calculate_indonesia_tax=1,
        tax_method="Progressive",
        is_december_override=0,
        ter_method_enabled=1,
    )
    wrapper = PayrollEntryIndonesia(doc)

    slip = types.SimpleNamespace(calculate_indonesia_tax=0, tax_method=None, is_december_override=0)

    wrapper.propagate_tax_settings_to_slips([slip])

    assert slip.calculate_indonesia_tax == 1
    assert slip.tax_method == "TER"
    assert slip.is_december_override == 0
