import unittest
import pytest

frappe = pytest.importorskip("frappe")
from payroll_indonesia.utils import get_ptkp_to_ter_mapping


class TestTaxUtils(unittest.TestCase):
    def setUp(self):
        if frappe.db.exists("Payroll Indonesia Settings", "Payroll Indonesia Settings"):
            self.settings = frappe.get_doc("Payroll Indonesia Settings")
        else:
            self.settings = frappe.new_doc("Payroll Indonesia Settings")

        self.settings.ptkp_ter_mapping_table = [
            {
                "doctype": "PTKP TER Mapping Entry",
                "ptkp_status": "TK1",
                "ter_category": "TER B",
            },
            {
                "doctype": "PTKP TER Mapping Entry",
                "ptkp_status": "K3",
                "ter_category": "TER C",
            },
        ]
        self.settings.flags.ignore_permissions = True
        self.settings.save()

    def tearDown(self):
        frappe.db.rollback()

    def test_ptkp_ter_mapping_cached(self):
        mapping1 = get_ptkp_to_ter_mapping()
        mapping2 = get_ptkp_to_ter_mapping()
        self.assertIs(mapping1, mapping2)
        self.assertEqual(mapping1["TK1"], "TER B")
        self.assertEqual(mapping1["K3"], "TER C")
