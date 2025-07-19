import unittest
import pytest

frappe = pytest.importorskip("frappe")

from payroll_indonesia.config.gl_account_mapper import (
    map_gl_account,
    get_gl_account_for_salary_component,
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

    def test_bpjs_alternate_employer_keyword(self):
        from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping import create_default_mapping
        from payroll_indonesia.payroll_indonesia.utils import get_or_create_account

        if not frappe.db.exists("BPJS Account Mapping", {"company": self.company}):
            create_default_mapping(self.company)
            frappe.db.commit()

        mapping_name = frappe.db.get_value("BPJS Account Mapping", {"company": self.company}, "name")
        mapping = frappe.get_doc("BPJS Account Mapping", mapping_name)

        mapping.jht_employer_debit_account = get_or_create_account(
            self.company,
            "BPJS JHT Employer Expense",
            "Expense Account",
            root_type="Expense",
        )
        mapping.jht_employee_account = get_or_create_account(
            self.company,
            "BPJS JHT Employee Expense",
            "Expense Account",
            root_type="Expense",
        )
        mapping.save(ignore_permissions=True)
        frappe.db.commit()

        account = get_gl_account_for_salary_component(self.company, "BPJS JHT Perusahaan")
        self.assertEqual(account, mapping.jht_employer_debit_account)
