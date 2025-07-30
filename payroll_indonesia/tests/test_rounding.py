import sys
import os
import types
import importlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# create dummy frappe module with minimal API
frappe = types.ModuleType("frappe")
utils_mod = types.ModuleType("frappe.utils")

def flt(val, precision=None):
    return float(val)

utils_mod.flt = flt

class ValidationError(Exception):
    pass

class DummyLogger:
    def info(self, msg):
        pass
    def warning(self, msg):
        pass

def logger():
    return DummyLogger()

frappe.utils = utils_mod
frappe.logger = logger
frappe.ValidationError = ValidationError

sys.modules.setdefault("frappe", frappe)
sys.modules.setdefault("frappe.utils", utils_mod)

pph21_ter = importlib.import_module("payroll_indonesia.config.pph21_ter")
from payroll_indonesia.utils import round_half_up


def test_round_half_up_basic():
    assert round_half_up(0.5) == 1
    assert round_half_up(1.5) == 2
    assert round_half_up(2.5) == 3


import pytest

@pytest.mark.parametrize("amount,expected", [(10, 1), (30, 2), (50, 3)])
def test_calculate_pph21_TER_rounding(monkeypatch, amount, expected):
    monkeypatch.setattr(pph21_ter, "get_ptkp_amount", lambda emp: 0)
    monkeypatch.setattr(pph21_ter, "get_ter_code", lambda emp: "A")
    monkeypatch.setattr(pph21_ter, "get_ter_rate", lambda code, pkp: 5)

    employee = {"employment_type": "Full-time", "tax_status": "TK0"}
    slip = {
        "earnings": [
            {
                "amount": amount,
                "is_tax_applicable": 1,
                "do_not_include_in_total": 0,
                "statistical_component": 0,
                "exempted_from_income_tax": 0,
            }
        ],
        "deductions": [],
    }
    result = pph21_ter.calculate_pph21_TER(employee, slip)
    assert result["pph21"] == expected
