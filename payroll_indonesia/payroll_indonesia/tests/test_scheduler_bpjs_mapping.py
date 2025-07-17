import unittest
import pytest

frappe = pytest.importorskip("frappe")

from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping import create_default_mapping


class TestSchedulerBPJSMapping(unittest.TestCase):
    def setUp(self):
        self.company = frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": "Scheduler Mapping Co",
                "abbr": "SMC",
                "default_currency": "IDR",
                "country": "Indonesia",
                "domain": "Services",
            }
        )
        if not frappe.db.exists("Company", self.company.name):
            self.company.insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    def test_create_default_mapping_callable(self):
        if frappe.db.exists("BPJS Account Mapping", {"company": self.company.name}):
            frappe.db.delete("BPJS Account Mapping", {"company": self.company.name})

        create_default_mapping(self.company.name)

        self.assertTrue(
            frappe.db.exists("BPJS Account Mapping", {"company": self.company.name})
        )

