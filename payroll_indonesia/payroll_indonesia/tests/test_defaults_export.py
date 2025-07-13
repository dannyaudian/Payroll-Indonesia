import json
import types
from pathlib import Path
import unittest
import pytest

frappe = pytest.importorskip("frappe")
from payroll_indonesia.payroll_indonesia import utils


class DummyRow:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def as_dict(self):
        return self.__dict__


class TestWriteDefaults(unittest.TestCase):
    def test_write_json_file_exports_settings(self, monkeypatch, tmp_path):
        monkeypatch.setattr(frappe, "get_app_path", lambda app: str(tmp_path))
        frappe.session = types.SimpleNamespace(user="tester")

        config_dir = Path(tmp_path) / "config"
        config_dir.mkdir()
        existing = {"app_info": {"version": "0.9", "last_updated": "old", "updated_by": "prev"}}
        with open(config_dir / "defaults.json", "w", encoding="utf-8") as f:
            json.dump(existing, f)

        doc = types.SimpleNamespace(
            sync_to_defaults=1,
            app_version="1.2.3",
            app_last_updated="new",
            app_updated_by="tester",
            kesehatan_employee_percent=1.0,
            kesehatan_employer_percent=4.0,
            kesehatan_max_salary=12000000.0,
            jht_employee_percent=2.0,
            jht_employer_percent=3.7,
            jp_employee_percent=1.0,
            jp_employer_percent=2.0,
            jp_max_salary=9000000.0,
            jkk_percent=0.24,
            jkm_percent=0.3,
            bpjs_account_mapping_json=json.dumps({"payment_account": "BPJS"}),
            umr_default=5000000.0,
            biaya_jabatan_percent=5.0,
            biaya_jabatan_max=500000.0,
            npwp_mandatory=0,
            tax_calculation_method="TER",
            use_ter=1,
            use_gross_up=0,
            ptkp_table=[DummyRow(ptkp_status="TK0", ptkp_amount=54000000.0)],
            ptkp_ter_mapping_table=[DummyRow(ptkp_status="TK0", ter_category="TER A")],
            tax_brackets_table=[DummyRow(income_from=0, income_to=60000000, tax_rate=5)],
            ter_rate_table=[
                DummyRow(status_pajak="TER A", income_from=0, income_to=5400000, rate=0)
            ],
            expense_accounts_json=json.dumps({"gaji": {"account_name": "Gaji"}}),
            payable_accounts_json=json.dumps({"pph": {"account_name": "Hutang"}}),
            parent_accounts_json=json.dumps({"root": {"account_name": "Payroll"}}),
            parent_account_candidates_expense="Expenses",
            parent_account_candidates_liability="Liabilities",
        )

        result = utils.write_json_file_if_enabled(doc)
        self.assertTrue(result)

        with open(config_dir / "defaults.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["app_info"]["last_updated"], "old")
        self.assertEqual(data["app_info"]["updated_by"], "prev")
        self.assertEqual(data["app_info"]["version"], "1.2.3")
        self.assertIn("bpjs", data)
        self.assertEqual(data["bpjs"]["kesehatan_employee_percent"], 1.0)
        self.assertIn("tax", data)
        self.assertEqual(data["tax"]["umr_default"], 5000000.0)
        self.assertIn("gl_accounts", data)
        self.assertIn("gaji", data["gl_accounts"]["expense_accounts"])


if __name__ == "__main__":
    unittest.main()
