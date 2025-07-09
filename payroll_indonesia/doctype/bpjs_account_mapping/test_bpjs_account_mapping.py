# -*- coding: utf-8 -*-
import unittest
import pytest

frappe = pytest.importorskip("frappe")
from frappe.utils import add_months, getdate

from ...bpjs_account_mapping import bpjs_account_mapping as mapping


class TestBPJSAccountMapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.company = frappe.get_doc({
            "doctype": "Company",
            "company_name": "BPJS Mapping Test Co",
            "abbr": "BMT",
            "default_currency": "IDR",
            "country": "Indonesia",
        })
        if not frappe.db.exists("Company", cls.company.name):
            cls.company.insert()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    def test_create_and_get_mapping(self):
        mapping_name = mapping.create_default_mapping(self.company.name)
        self.assertTrue(mapping_name)

        result = mapping.get_mapping_for_company(self.company.name)
        self.assertEqual(result["company"], self.company.name)
        self.assertIn("payable_account", result)

