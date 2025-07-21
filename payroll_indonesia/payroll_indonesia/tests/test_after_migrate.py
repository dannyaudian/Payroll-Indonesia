import unittest
from unittest.mock import patch
import json
import pytest

frappe = pytest.importorskip("frappe")
from payroll_indonesia.setup import setup_module
from payroll_indonesia.payroll_indonesia.utils import get_or_create_account


class TestAfterMigrateBPJSMapping(unittest.TestCase):
    def setUp(self):
        self.company = frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": "BPJS Mapping Test Co",
                "abbr": "BMTC",
                "default_currency": "IDR",
                "country": "Indonesia",
                "domain": "Services",
            }
        )
        if not frappe.db.exists("Company", self.company.name):
            self.company.insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    def test_after_migrate_creates_mapping(self):
        if frappe.db.exists("BPJS Account Mapping", {"company": self.company.name}):
            frappe.db.delete("BPJS Account Mapping", {"company": self.company.name})
        with patch.object(setup_module, "setup_accounts", return_value=True), patch.object(
            setup_module, "_load_defaults", return_value=None
        ), patch("payroll_indonesia.fixtures.setup.setup_default_salary_structure"), patch(
            "payroll_indonesia.fixtures.setup.setup_salary_components"
        ):
            setup_module.after_migrate()
        self.assertTrue(frappe.db.exists("BPJS Account Mapping", {"company": self.company.name}))

    def test_bpjs_json_migrated(self):
        settings = frappe.get_single("Payroll Indonesia Settings")
        settings.company = self.company.name
        settings.bpjs_account_mapping_json = json.dumps(
            {
                "kesehatan_employee_account": "BPJS Kesehatan Payable",
                "kesehatan_employer_debit_account": "BPJS Kesehatan Employer Expense",
            }
        )
        settings.flags.ignore_permissions = True
        settings.save()

        get_or_create_account(
            self.company.name,
            "BPJS Kesehatan Payable",
            "Payable",
            root_type="Liability",
        )
        get_or_create_account(
            self.company.name,
            "BPJS Kesehatan Employer Expense",
            "Expense Account",
            root_type="Expense",
        )

        if frappe.db.exists("BPJS Account Mapping", {"company": self.company.name}):
            frappe.db.delete("BPJS Account Mapping", {"company": self.company.name})

        with patch.object(setup_module, "setup_accounts", return_value=True), patch.object(
            setup_module, "_load_defaults", return_value=None
        ), patch("payroll_indonesia.fixtures.setup.setup_default_salary_structure"), patch(
            "payroll_indonesia.fixtures.setup.setup_salary_components"
        ):
            setup_module.after_migrate()

        name = frappe.db.get_value("BPJS Account Mapping", {"company": self.company.name}, "name")
        doc = frappe.get_doc("BPJS Account Mapping", name)
        self.assertEqual(
            doc.kesehatan_employee_account,
            f"BPJS Kesehatan Payable - {self.company.abbr}",
        )
        self.assertEqual(
            doc.kesehatan_employer_debit_account,
            f"BPJS Kesehatan Employer Expense - {self.company.abbr}",
        )


if __name__ == "__main__":
    unittest.main()
