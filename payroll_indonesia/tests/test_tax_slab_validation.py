import sys
import types
import importlib
from unittest.mock import MagicMock
import pytest

pytest.importorskip("frappe")


def setup_frappe_stub():
    frappe = types.ModuleType("frappe")
    frappe._ = lambda x: x

    class _dict(dict):
        def __getattr__(self, item):
            return self[item]
    frappe._dict = _dict

    frappe.db = types.SimpleNamespace()
    frappe.get_cached_doc = MagicMock(return_value=types.SimpleNamespace(tax_calculation_method="PROGRESSIVE", use_ter=0))
    frappe.utils = types.ModuleType("frappe.utils")
    frappe.utils.flt = float
    frappe.utils.cint = int
    frappe.utils.getdate = lambda *a, **k: None
    frappe.utils.now_datetime = lambda: None
    frappe.utils.add_to_date = lambda *a, **k: None
    sys.modules["frappe.utils"] = frappe.utils
    model_module = types.ModuleType("frappe.model")
    document_module = types.ModuleType("frappe.model.document")

    class Document:
        pass

    document_module.Document = Document
    sys.modules["frappe.model"] = model_module
    sys.modules["frappe.model.document"] = document_module
    frappe.conf = {}
    frappe.utils = types.ModuleType("frappe.utils")
    frappe.utils.now_datetime = lambda: None
    frappe.utils.add_to_date = lambda *a, **k: None
    sys.modules["frappe.utils"] = frappe.utils

    sys.modules["frappe"] = frappe
    return frappe


def setup_salary_slip_stub():
    hrms_pkg = types.ModuleType("hrms")
    payroll_pkg = types.ModuleType("hrms.payroll")
    doctype_pkg = types.ModuleType("hrms.payroll.doctype")
    ss_pkg = types.ModuleType("hrms.payroll.doctype.salary_slip")
    ss_module = types.ModuleType("hrms.payroll.doctype.salary_slip.salary_slip")

    class SalarySlip:
        def __init__(self, *a, **k):
            pass

        def validate(self):
            # mimic ERPNext access to allow_tax_exemption
            self.tax_slab.allow_tax_exemption

    ss_module.SalarySlip = SalarySlip
    sys.modules["hrms"] = hrms_pkg
    sys.modules["hrms.payroll"] = payroll_pkg
    sys.modules["hrms.payroll.doctype"] = doctype_pkg
    sys.modules["hrms.payroll.doctype.salary_slip"] = ss_pkg
    sys.modules["hrms.payroll.doctype.salary_slip.salary_slip"] = ss_module



def test_validate_sets_default_tax_slab(monkeypatch):
    frappe = setup_frappe_stub()
    setup_salary_slip_stub()

    controller = importlib.import_module("payroll_indonesia.override.salary_slip.controller")
    Slip = controller.IndonesiaPayrollSalarySlip

    slip = Slip()
    slip.tax_slab = None
    # should not raise
    Slip.validate(slip)
    assert getattr(slip.tax_slab, "allow_tax_exemption") == 0

    slip.tax_slab = "invalid"
    Slip.validate(slip)
    assert getattr(slip.tax_slab, "allow_tax_exemption") == 0

