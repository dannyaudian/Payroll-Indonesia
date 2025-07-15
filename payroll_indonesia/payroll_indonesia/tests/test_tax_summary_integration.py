import sys
import types
from unittest.mock import MagicMock
import pytest

frappe = pytest.importorskip("frappe")


def _setup_frappe(new_doc=None, get_doc=None):
    if new_doc is None:
        new_doc = MagicMock()
    if get_doc is None:
        get_doc = MagicMock()
    fake = types.ModuleType("frappe")
    fake.utils = types.SimpleNamespace(flt=float, cint=int)
    fake.db = types.SimpleNamespace(get_value=MagicMock(return_value=None))
    fake.new_doc = new_doc
    fake.get_doc = get_doc
    fake.as_json = lambda x: "{}"
    fake.msgprint = lambda *a, **k: None
    sys.modules["frappe"] = fake
    sys.modules["frappe.utils"] = fake.utils
    return fake


def test_creates_summary_when_missing(monkeypatch):
    new_summary = types.SimpleNamespace(
        flags=types.SimpleNamespace(), insert=MagicMock()
    )
    fake = _setup_frappe(new_doc=MagicMock(return_value=new_summary))

    import importlib
    controller = importlib.import_module(
        "payroll_indonesia.override.salary_slip.controller"
    )

    monkeypatch.setattr(controller, "get_slip_year_month", lambda doc: (2025, 1))
    logs = []
    monkeypatch.setattr(
        controller,
        "logger",
        types.SimpleNamespace(
            info=lambda msg: logs.append(("info", msg)),
            warning=lambda msg: logs.append(("warning", msg)),
            debug=lambda *a, **k: None,
            exception=lambda *a, **k: None,
        ),
    )

    doc = types.SimpleNamespace(
        employee="EMP-1",
        calculate_indonesia_tax=1,
        tax_method="Progressive",
        ytd_gross_pay=100,
        ytd_tax=10,
        ytd_bpjs=5,
        ytd_taxable_components=80,
        ytd_tax_deductions=5,
    )

    controller.ensure_employee_tax_summary_integration(doc)

    fake.new_doc.assert_called_once_with("Employee Tax Summary")
    assert new_summary.employee == "EMP-1"
    assert new_summary.year == 2025
    assert new_summary.tax_method == "Progressive"
    assert any(l[0] == "info" for l in logs)
    assert new_summary.insert.called


def test_sync_existing_summary(monkeypatch):
    existing = types.SimpleNamespace(
        employee="EMP-1",
        year=2025,
        tax_method="TER",
        ytd_gross_pay=0,
        ytd_tax=0,
        ytd_bpjs=0,
        ytd_taxable_components=0,
        ytd_tax_deductions=0,
        flags=types.SimpleNamespace(),
        save=MagicMock(),
    )
    get_doc = MagicMock(return_value=existing)
    fake = _setup_frappe(get_doc=get_doc)
    fake.db.get_value = MagicMock(return_value="TAX-001")

    import importlib
    controller = importlib.import_module(
        "payroll_indonesia.override.salary_slip.controller"
    )

    monkeypatch.setattr(controller, "get_slip_year_month", lambda doc: (2025, 1))
    logs = []
    monkeypatch.setattr(
        controller,
        "logger",
        types.SimpleNamespace(
            info=lambda msg: logs.append(("info", msg)),
            warning=lambda msg: logs.append(("warning", msg)),
            debug=lambda *a, **k: None,
            exception=lambda *a, **k: None,
        ),
    )

    doc = types.SimpleNamespace(
        employee="EMP-1",
        calculate_indonesia_tax=1,
        tax_method="Progressive",
        ytd_gross_pay=100,
        ytd_tax=10,
        ytd_bpjs=5,
        ytd_taxable_components=80,
        ytd_tax_deductions=5,
    )

    controller.ensure_employee_tax_summary_integration(doc)

    get_doc.assert_called_once_with("Employee Tax Summary", "TAX-001")
    assert existing.tax_method == "Progressive"
    assert existing.ytd_gross_pay == 100
    assert any(l[0] == "warning" for l in logs)
    assert existing.save.called

