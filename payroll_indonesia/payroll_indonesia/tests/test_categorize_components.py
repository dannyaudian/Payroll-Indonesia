import types
import importlib
import pytest

pytest.importorskip("frappe")


def _make_row(name, amount):
    return types.SimpleNamespace(salary_component=name, amount=amount)


def test_categorize_components_various_tax_effects(monkeypatch):
    tax_mod = importlib.import_module(
        "payroll_indonesia.override.salary_slip.tax_calculator"
    )

    mapping = {
        "Gaji Pokok": "Penambah Bruto/Objek Pajak",
        "Natura Rumah": "Natura/Fasilitas (Objek Pajak)",
        "Tunjangan Non Pajak": "Tidak Berpengaruh ke Pajak",
        "Iuran Pensiun": "Pengurang Netto/Tax Deduction",
        "Potongan Non Pajak": "Tidak Berpengaruh ke Pajak",
    }

    monkeypatch.setattr(
        tax_mod,
        "get_component_tax_effect",
        lambda component, comp_type=None: mapping.get(component, "Tidak Berpengaruh ke Pajak"),
    )

    slip = types.SimpleNamespace(
        earnings=[
            _make_row("Gaji Pokok", 1_000_000),
            _make_row("Natura Rumah", 200_000),
            _make_row("Tunjangan Non Pajak", 300_000),
        ],
        deductions=[
            _make_row("Iuran Pensiun", 100_000),
            _make_row("Potongan Non Pajak", 50_000),
        ],
    )

    result = tax_mod.categorize_components_by_tax_effect(slip)

    assert result["penambah_bruto"]["Gaji Pokok"] == 1_000_000
    assert result["pengurang_netto"]["Iuran Pensiun"] == 100_000
    assert result["tidak_berpengaruh"]["Tunjangan Non Pajak"] == 300_000
    assert result["natura_objek"]["Natura Rumah"] == 200_000
    assert result["tidak_berpengaruh"]["Potongan Non Pajak"] == 50_000
    assert result["total"]["penambah_bruto"] == 1_000_000
    assert result["total"]["pengurang_netto"] == 100_000
    assert result["total"]["tidak_berpengaruh"] == 350_000
    assert result["total"]["natura_objek"] == 200_000
    assert result["total"]["natura_non_objek"] == 0


def test_categorize_components_december(monkeypatch):
    tax_mod = importlib.import_module(
        "payroll_indonesia.override.salary_slip.tax_calculator"
    )

    mapping = {
        "Tunjangan Akhir Tahun": "Penambah Bruto/Objek Pajak",
        "Bonus Tahun Baru": "Natura/Fasilitas (Non-Objek Pajak)",
    }

    monkeypatch.setattr(
        tax_mod,
        "get_component_tax_effect",
        lambda component, comp_type=None: mapping.get(component, "Tidak Berpengaruh ke Pajak"),
    )

    slip = types.SimpleNamespace(
        is_december_override=1,
        earnings=[
            _make_row("Tunjangan Akhir Tahun", 5_000_000),
            _make_row("Bonus Tahun Baru", 1_000_000),
        ],
        deductions=[],
    )

    assert tax_mod.is_december_calculation(slip)

    result = tax_mod.categorize_components_by_tax_effect(slip)

    assert result["penambah_bruto"]["Tunjangan Akhir Tahun"] == 5_000_000
    assert result["natura_non_objek"]["Bonus Tahun Baru"] == 1_000_000
    assert result["total"]["penambah_bruto"] == 5_000_000
    assert result["total"]["natura_non_objek"] == 1_000_000
