import sys
import types
import importlib
import pytest

pytest.importorskip("frappe")


def test_biaya_jabatan_calculation(monkeypatch):
    # Import target module dynamically
    tax_mod = importlib.import_module(
        "payroll_indonesia.override.salary_slip.tax_calculator"
    )

    # Stub helper functions used by calculation
    monkeypatch.setattr(tax_mod, "get_tax_status", lambda slip: slip.status_pajak)
    monkeypatch.setattr(tax_mod, "get_ptkp_value", lambda status: 0)
    monkeypatch.setattr(tax_mod, "calculate_progressive_tax", lambda pkp: (0, []))
    monkeypatch.setattr(
        tax_mod,
        "categorize_components_by_tax_effect",
        lambda slip: {
            "total": {
                "penambah_bruto": slip.gross_pay,
                "pengurang_netto": 0,
                "natura_objek": 0,
            }
        },
    )

    slip = types.SimpleNamespace(gross_pay=10000000, status_pajak="TK0")

    tax, details = tax_mod.calculate_monthly_pph_progressive(slip)

    expected = min(
        details["annual_taxable"] * tax_mod.BIAYA_JABATAN_PERCENT / 100,
        tax_mod.BIAYA_JABATAN_MAX * tax_mod.MONTHS_PER_YEAR,
    )
    assert details["biaya_jabatan"] == expected

    # Check cap when income is high
    slip_high = types.SimpleNamespace(gross_pay=30000000, status_pajak="TK0")
    tax, details = tax_mod.calculate_monthly_pph_progressive(slip_high)
    assert details["biaya_jabatan"] == tax_mod.BIAYA_JABATAN_MAX * tax_mod.MONTHS_PER_YEAR
