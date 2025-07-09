import importlib.util
import sys
import types
from pathlib import Path
import pytest


def load_module(rate):
    # create minimal frappe stub
    frappe = types.ModuleType("frappe")
    frappe._ = lambda x: x
    frappe.get_cached_doc = lambda *a, **k: types.SimpleNamespace(
        ter_rate_table=[
            types.SimpleNamespace(
                status_pajak="TER A",
                income_from=0,
                income_to=0,
                is_highest_bracket=1,
                rate=rate,
            )
        ]
    )
    utils_mod = types.ModuleType("frappe.utils")
    utils_mod.flt = float
    utils_mod.cint = int
    utils_mod.getdate = lambda *a, **k: None
    utils_mod.now_datetime = lambda: None
    utils_mod.add_to_date = lambda *a, **k: None
    frappe.utils = utils_mod
    frappe.conf = {}
    model_mod = types.ModuleType("frappe.model")
    document_mod = types.ModuleType("frappe.model.document")

    class Document:
        pass

    document_mod.Document = Document

    sys.modules["frappe"] = frappe
    sys.modules["frappe.utils"] = utils_mod
    sys.modules["frappe.model"] = model_mod
    sys.modules["frappe.model.document"] = document_mod

    module_path = (
        Path(__file__).resolve().parents[2]
        / "override"
        / "salary_slip"
        / "tax_calculator.py"
    )
    spec = importlib.util.spec_from_file_location("tax_calculator", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_percentage_rate_converted(monkeypatch):
    tc = load_module(2.5)
    monkeypatch.setattr(tc.cache_utils, "get_cache", lambda *a, **k: None)
    monkeypatch.setattr(tc.cache_utils, "set_cache", lambda *a, **k: None)
    rate = tc.get_ter_rate("TER A", 1000000)
    assert rate == pytest.approx(0.025)


def test_fractional_rate_unchanged(monkeypatch):
    tc = load_module(0.05)
    monkeypatch.setattr(tc.cache_utils, "get_cache", lambda *a, **k: None)
    monkeypatch.setattr(tc.cache_utils, "set_cache", lambda *a, **k: None)
    rate = tc.get_ter_rate("TER A", 1000000)
    assert rate == pytest.approx(0.05)
