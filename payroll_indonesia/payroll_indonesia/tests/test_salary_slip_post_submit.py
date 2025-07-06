import sys
import types
import datetime
from unittest.mock import MagicMock


def test_post_submit_updates_existing_history(monkeypatch):
    # create minimal frappe stub only for this test
    frappe = types.ModuleType("frappe")
    frappe.db = types.SimpleNamespace(exists=lambda *a, **k: True)
    frappe.get_doc = MagicMock()
    frappe.new_doc = MagicMock()
    frappe.utils = types.ModuleType("frappe.utils")
    frappe.utils.flt = float
    frappe.utils.cint = int
    frappe.utils.getdate = lambda *a, **k: datetime.date.today()
    frappe.utils.date_diff = lambda a, b: 0
    frappe.utils.add_months = lambda d, m: d
    frappe.utils.get_first_day = lambda d: d
    frappe.utils.get_last_day = lambda d: d
    frappe.utils.add_days = lambda d, n=0: d
    bg = types.ModuleType("frappe.utils.background_jobs")
    bg.enqueue = MagicMock()
    frappe.utils.background_jobs = bg
    frappe._ = lambda x: x
    frappe.throw = lambda msg: (_ for _ in ()).throw(Exception(msg))

    # Minimal Document class for frappe.model.document import
    model_module = types.ModuleType("frappe.model")
    document_module = types.ModuleType("frappe.model.document")
    class Document: ...
    document_module.Document = Document

    sys.modules["frappe.model"] = model_module
    sys.modules["frappe.model.document"] = document_module

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = frappe.utils
    sys.modules["frappe.utils.background_jobs"] = bg

    # stub hrms.salary_slip import used by controller
    hrms_pkg = types.ModuleType("hrms")
    payroll_pkg = types.ModuleType("hrms.payroll")
    doctype_pkg = types.ModuleType("hrms.payroll.doctype")
    ss_pkg = types.ModuleType("hrms.payroll.doctype.salary_slip")
    ss_module = types.ModuleType("hrms.payroll.doctype.salary_slip.salary_slip")

    class SalarySlip:  # minimal stand-in
        pass

    ss_module.SalarySlip = SalarySlip
    sys.modules["hrms"] = hrms_pkg
    sys.modules["hrms.payroll"] = payroll_pkg
    sys.modules["hrms.payroll.doctype"] = doctype_pkg
    sys.modules["hrms.payroll.doctype.salary_slip"] = ss_pkg
    sys.modules["hrms.payroll.doctype.salary_slip.salary_slip"] = ss_module

    # minimal utils module used by salary_slip_functions
    pi_utils = types.ModuleType("payroll_indonesia.payroll_indonesia.utils")
    pi_utils.calculate_bpjs = lambda base_salary, rate_percent, max_salary=None: 0
    sys.modules["payroll_indonesia.payroll_indonesia.utils"] = pi_utils

    import importlib
    ssf = importlib.import_module("payroll_indonesia.override.salary_slip_functions")

    class DummyHistory:
        def __init__(self):
            self.ytd_gross = 0
            self.ytd_tax = 0
            self.flags = types.SimpleNamespace()
        def save(self):
            self.saved = True

    existing = DummyHistory()
    frappe.db.exists = lambda *a, **k: True
    frappe.get_doc.return_value = existing

    slip = MagicMock(
        name="SS-001", employee="EMP-1", posting_date="2025-01-31",
        gross_pay=1000, pph21=50, deductions=[], docstatus=1
    )

    monkeypatch.setattr(ssf, "calculate_employer_contributions", lambda doc: {})
    monkeypatch.setattr(ssf, "store_employer_contributions", lambda doc, c: None)
    monkeypatch.setattr(ssf, "enqueue_tax_summary_update", lambda doc: None)

    ssf.salary_slip_post_submit(slip)

    assert existing.ytd_gross == 1000
    assert existing.ytd_tax == 50
    assert getattr(existing, "saved", False)

