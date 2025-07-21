import unittest
import pytest

pytest.importorskip("frappe")

from payroll_indonesia.config.gl_mapper_core import get_account_mapping_from_defaults


class TestAccountMappingFromDefaults(unittest.TestCase):
    def test_bilingual_mapping(self):
        mapping = get_account_mapping_from_defaults()
        self.assertEqual(mapping.get("Gaji Pokok"), "Beban Gaji Pokok")
        self.assertEqual(mapping.get("Basic Salary"), "Beban Gaji Pokok")
        self.assertEqual(mapping.get("Bonus"), "Beban Bonus")
        self.assertEqual(mapping.get("Tunjangan Makan"), "Beban Tunjangan Makan")
        self.assertEqual(mapping.get("Meal Allowance"), "Beban Tunjangan Makan")

    def test_non_bilingual_option(self):
        mapping = get_account_mapping_from_defaults(bilingual=False)
        self.assertIn("Gaji Pokok", mapping)
        self.assertNotIn("Basic Salary", mapping)
