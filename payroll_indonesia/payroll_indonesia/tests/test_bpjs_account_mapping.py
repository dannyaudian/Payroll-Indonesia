import unittest
import pytest

frappe = pytest.importorskip("frappe")

from payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping import (
    create_default_mapping,
    get_mapping_for_company,
    ACCOUNT_FIELDS,
)
from payroll_indonesia.payroll_indonesia.utils import get_or_create_account


class TestBPJSAccountMapping(unittest.TestCase):
    def setUp(self):
        self.company = frappe.get_doc({
            "doctype": "Company",
            "company_name": "BPJS Mapping Doc Co",
            "abbr": "BMD",
            "default_currency": "IDR",
            "country": "Indonesia",
            "domain": "Services",
        })
        if not frappe.db.exists("Company", self.company.name):
            self.company.insert(ignore_permissions=True)

        self.other_company = frappe.get_doc({
            "doctype": "Company",
            "company_name": "Other BPJS Co",
            "abbr": "OBC",
            "default_currency": "IDR",
            "country": "Indonesia",
            "domain": "Services",
        })
        if not frappe.db.exists("Company", self.other_company.name):
            self.other_company.insert(ignore_permissions=True)

    def tearDown(self):
        frappe.db.rollback()

    def test_create_default_mapping_has_all_fields(self):
        if frappe.db.exists("BPJS Account Mapping", {"company": self.company.name}):
            frappe.db.delete("BPJS Account Mapping", {"company": self.company.name})

        name = create_default_mapping(self.company.name)
        self.assertTrue(frappe.db.exists("BPJS Account Mapping", name))

        doc = frappe.get_doc("BPJS Account Mapping", name)
        for field in ACCOUNT_FIELDS:
            self.assertTrue(hasattr(doc, field))
            self.assertEqual(doc.get(field), "")

    def test_get_mapping_for_company_includes_fields(self):
        if not frappe.db.exists("BPJS Account Mapping", {"company": self.company.name}):
            create_default_mapping(self.company.name)

        mapping_dict = get_mapping_for_company(self.company.name)
        for field in ACCOUNT_FIELDS:
            self.assertIn(field, mapping_dict)

    def test_validate_accounts_wrong_company(self):
        wrong_acc = get_or_create_account(
            self.other_company.name,
            "Wrong Expense",
            "Expense Account",
            root_type="Expense",
        )

        if frappe.db.exists("BPJS Account Mapping", {"company": self.company.name}):
            mapping = frappe.get_doc(
                "BPJS Account Mapping",
                frappe.db.get_value("BPJS Account Mapping", {"company": self.company.name})
            )
        else:
            name = create_default_mapping(self.company.name)
            mapping = frappe.get_doc("BPJS Account Mapping", name)

        mapping.kesehatan_employee_account = wrong_acc
        with self.assertRaises(frappe.ValidationError):
            mapping.save(ignore_permissions=True)

