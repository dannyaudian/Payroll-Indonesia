import sys
import types
from unittest.mock import MagicMock


def setup_frappe_stub():
    frappe = types.ModuleType("frappe")
    frappe._ = lambda x: x

    class _dict(dict):
        def __getattr__(self, item):
            return self[item]
    frappe._dict = _dict

    frappe.db = types.SimpleNamespace()
    frappe.get_cached_doc = MagicMock(return_value=types.SimpleNamespace(tax_calculation_method="PROGRESSIVE", use_ter=0))

    utils = types.ModuleType("frappe.utils")
    utils.flt = float
    utils.getdate = lambda *a, **k: None
    utils.cint = int
    frappe.utils = utils
    sys.modules["frappe.utils"] = utils

    model_module = types.ModuleType("frappe.model")
    document_module = types.ModuleType("frappe.model.document")

    class Document:
        pass

    document_module.Document = Document

    sys.modules["frappe.model"] = model_module
    sys.modules["frappe.model.document"] = document_module

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

    # stub dependencies required by controller
    override_pkg = types.ModuleType("payroll_indonesia.override")
    override_pkg.__path__ = []
    salary_slip_pkg = types.ModuleType("payroll_indonesia.override.salary_slip")
    salary_slip_pkg.__path__ = []
    sys.modules["payroll_indonesia.override"] = override_pkg
    sys.modules["payroll_indonesia.override.salary_slip"] = salary_slip_pkg

    tax_calc_module = types.ModuleType("payroll_indonesia.override.salary_slip.tax_calculator")
    sys.modules["payroll_indonesia.override.salary_slip.tax_calculator"] = tax_calc_module

    utils_module = types.ModuleType("payroll_indonesia.payroll_indonesia.utils")
    utils_module.get_status_pajak = lambda *a, **k: ""
    utils_module.get_ptkp_to_ter_mapping = lambda: {}
    utils_module.get_ter_rate = lambda *a, **k: 0
    sys.modules["payroll_indonesia.payroll_indonesia.utils"] = utils_module



def test_validate_sets_default_tax_slab(monkeypatch):
    frappe = setup_frappe_stub()
    setup_salary_slip_stub()

    import importlib.util
    from pathlib import Path

    controller_path = Path(__file__).resolve().parents[2] / "override" / "salary_slip" / "controller.py"
    spec = importlib.util.spec_from_file_location("controller", controller_path)
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    Slip = controller.IndonesiaPayrollSalarySlip

    slip = Slip()
    slip.tax_slab = None
    # should not raise
    Slip.validate(slip)
    assert getattr(slip.tax_slab, "allow_tax_exemption") == 0
    assert getattr(slip.tax_slab, "slabs") == []

    slip.tax_slab = "invalid"
    Slip.validate(slip)
    assert getattr(slip.tax_slab, "allow_tax_exemption") == 0
    assert getattr(slip.tax_slab, "slabs") == []

