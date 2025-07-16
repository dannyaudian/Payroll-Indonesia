import sys
import types
from unittest.mock import MagicMock
import importlib
import pytest

pytest.importorskip("frappe")


def _setup_frappe(companies):
    created = []

    class DummyDoc:
        def __init__(self):
            self.slabs = []
            self.flags = types.SimpleNamespace()
            self.insert = MagicMock()

        def append(self, field, row):
            getattr(self, field).append(row)

    def new_doc(dt):
        doc = DummyDoc()
        created.append(doc)
        return doc

    fake = types.ModuleType("frappe")
    fake._ = lambda x: x
    fake.defaults = types.SimpleNamespace(get_global_default=lambda key: None)
    fake.get_all = lambda dt, pluck=None: companies if dt == "Company" else []

    def exists(dt, name=None):
        if dt == "DocType" and name == "Income Tax Slab":
            return True
        if dt == "Income Tax Slab":
            return False
        return False

    fake.db = types.SimpleNamespace(
        exists=exists,
        has_column=lambda dt, col: True,
        commit=lambda: None,
    )
    fake.new_doc = new_doc
    fake.utils = types.ModuleType("frappe.utils")
    fake.utils.flt = float
    fake.utils.cint = int
    sys.modules["frappe"] = fake
    sys.modules["frappe.utils"] = fake.utils
    return fake, created


def test_uses_first_company_when_default_missing(monkeypatch):
    fake, created = _setup_frappe(["ACME"])
    module = importlib.reload(importlib.import_module("payroll_indonesia.utilities.tax_slab"))
    logs = []
    monkeypatch.setattr(
        module,
        "logger",
        types.SimpleNamespace(
            info=lambda msg: logs.append(("info", msg)),
            warning=lambda msg: logs.append(("warning", msg)),
            error=lambda *a, **k: None,
            debug=lambda *a, **k: None,
        ),
    )

    result = module.setup_income_tax_slab()

    assert result is True
    assert created and created[0].company == "ACME"
    assert created[0].flags.ignore_mandatory is True


def test_returns_false_when_no_company(monkeypatch):
    fake, created = _setup_frappe([])
    module = importlib.reload(importlib.import_module("payroll_indonesia.utilities.tax_slab"))
    logs = []
    monkeypatch.setattr(
        module,
        "logger",
        types.SimpleNamespace(
            info=lambda msg: logs.append(("info", msg)),
            warning=lambda msg: logs.append(("warning", msg)),
            error=lambda *a, **k: None,
            debug=lambda *a, **k: None,
        ),
    )

    result = module.setup_income_tax_slab()

    assert result is False
    assert not created
    assert any(l[0] == "warning" for l in logs)

