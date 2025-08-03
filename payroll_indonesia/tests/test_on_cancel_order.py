import sys
import types
import json
import datetime


def test_on_cancel_respects_tax_type_and_dates():
    # Setup minimal frappe environment
    frappe = types.SimpleNamespace()

    class DummyLogger:
        def info(self, *a, **k):
            pass

        def warning(self, *a, **k):
            pass

        def error(self, *a, **k):
            pass

    frappe.logger = lambda *a, **k: DummyLogger()
    frappe.msgprint = lambda *a, **k: None
    frappe.db = types.SimpleNamespace(
        savepoint=lambda name: None,
        rollback=lambda save_point=None: None,
        commit=lambda: None,
    )
    frappe.utils = types.SimpleNamespace(
        flt=float, getdate=lambda d: datetime.datetime.strptime(d, "%Y-%m-%d")
    )
    frappe.model = types.SimpleNamespace()
    frappe.model.document = types.SimpleNamespace(Document=object)

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = frappe.utils
    sys.modules["frappe.model.document"] = frappe.model.document

    from payroll_indonesia.payroll_indonesia.doctype.annual_payroll_history.annual_payroll_history import (
        AnnualPayrollHistory,
    )

    # Prepare dummy salary slips
    cancelled = []

    class Slip:
        def __init__(
            self,
            name,
            posting_date=None,
            start_date=None,
            tax_type=None,
            pph21_info=None,
        ):
            self.name = name
            self.posting_date = posting_date
            self.start_date = start_date
            self.tax_type = tax_type
            self.pph21_info = pph21_info
            self.flags = types.SimpleNamespace()

        def cancel(self):
            cancelled.append(self.name)

    slips = {
        "SS-DEC1": Slip("SS-DEC1", posting_date="2024-12-15", tax_type="DECEMBER"),
        "SS-DEC2": Slip(
            "SS-DEC2",
            start_date="2024-12-01",
            pph21_info=json.dumps({"_tax_type": "DECEMBER"}),
        ),
        "SS-NOV": Slip("SS-NOV", start_date="2024-11-01"),
        "SS-OCT": Slip("SS-OCT", posting_date="2024-10-01"),
    }

    frappe.get_doc = lambda dt, name: slips[name]

    class Detail:
        def __init__(self, name):
            self.salary_slip = name

    history = AnnualPayrollHistory()
    history.name = "APH-1"
    history.monthly_details = [
        Detail("SS-OCT"),
        Detail("SS-DEC2"),
        Detail("SS-NOV"),
        Detail("SS-DEC1"),
    ]

    history.on_cancel()

    assert cancelled == ["SS-DEC1", "SS-DEC2", "SS-NOV", "SS-OCT"]

