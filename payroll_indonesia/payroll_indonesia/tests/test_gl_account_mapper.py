import unittest
import pytest

frappe = pytest.importorskip("frappe")

from payroll_indonesia.config.gl_account_mapper import (
    map_gl_account,
    get_gl_account_for_salary_component,
    get_expense_account_for_component,
)


class TestGLAccountMapper(unittest.TestCase):
    def setUp(self):
        self.company = frappe.defaults.get_user_default("Company")
        self.company_abbr = frappe.get_cached_value("Company", self.company, "abbr")

    def tearDown(self):
        frappe.db.rollback()

    def test_account_created_once(self):
        acc1 = map_gl_account(self.company, "beban_gaji_pokok", "expense_accounts")
        acc2 = map_gl_account(self.company, "beban_gaji_pokok", "expense_accounts")
        self.assertEqual(acc1, acc2)
        self.assertTrue(frappe.db.exists("Account", acc1))
        doubled = f"{acc1} - {self.company_abbr}"
        self.assertFalse(frappe.db.exists("Account", doubled))

    def test_unmapped_component_account_auto_created(self):
        comp_name = "Komisi Spesial"
        gl_account = get_gl_account_for_salary_component(self.company, comp_name)
        self.assertTrue(frappe.db.exists("Account", gl_account))
        self.assertTrue(gl_account.endswith(f" - {self.company_abbr}"))

    def test_english_component_names_map_correctly(self):
        """Ensure English salary component names map to the same accounts."""

        pairs = [
            ("Gaji Pokok", "Basic Salary"),
            ("Tunjangan Makan", "Meal Allowance"),
            ("Tunjangan Transport", "Transport Allowance"),
        ]

        for indo, english in pairs:
            account_indo = get_gl_account_for_salary_component(self.company, indo)
            account_eng = get_gl_account_for_salary_component(
                self.company, english
            )
            self.assertEqual(account_indo, account_eng)

    def test_get_expense_account_helper(self):
        self.assertEqual(
            get_expense_account_for_component("Gaji Pokok"),
            "Beban Gaji Pokok",
        )
        self.assertEqual(
            get_expense_account_for_component("Basic Salary"),
            "Beban Gaji Pokok",
        )
        self.assertIsNone(get_expense_account_for_component("Unknown"))
