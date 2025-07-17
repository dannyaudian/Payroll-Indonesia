import unittest
import pytest

frappe = pytest.importorskip("frappe")

from payroll_indonesia.payroll_indonesia.utils import get_or_create_account


class TestAccountCreation(unittest.TestCase):
    def setUp(self):
        self.company = frappe.defaults.get_user_default("Company")
        self.company_abbr = frappe.get_cached_value("Company", self.company, "abbr")

    def tearDown(self):
        frappe.db.rollback()

    def test_get_or_create_account_creates_once(self):
        acc = get_or_create_account(
            self.company,
            "Test Payroll Expense",
            "Expense Account",
            root_type="Expense",
        )
        self.assertTrue(frappe.db.exists("Account", acc))
        again = get_or_create_account(
            self.company,
            "Test Payroll Expense",
            "Expense Account",
            root_type="Expense",
        )
        self.assertEqual(acc, again)
        doubled = f"{acc} - {self.company_abbr}"
        self.assertFalse(frappe.db.exists("Account", doubled))
