import unittest
from unittest.mock import patch
import pytest

frappe = pytest.importorskip("frappe")
from payroll_indonesia.setup import setup_module


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


if __name__ == "__main__":
    unittest.main()
