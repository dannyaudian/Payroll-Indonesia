import unittest
import pytest

frappe = pytest.importorskip("frappe")

from payroll_indonesia.fixtures import setup as setup_module
from payroll_indonesia.config.config import get_config as get_default_config


class TestSetupCompanyAccounts(unittest.TestCase):
    def setUp(self):
        self.company = frappe.defaults.get_user_default("Company")

    def tearDown(self):
        frappe.db.rollback()

    def test_maps_all_expense_accounts(self):
        config = get_default_config()
        expected_keys = list(config.get("gl_accounts", {}).get("expense_accounts", {}).keys())

        salary_components = [
            c["name"] for c in config.get("salary_components", {}).get("earnings", [])
        ]
        salary_components += [
            c["name"] for c in config.get("salary_components", {}).get("deductions", [])
        ]

        with unittest.mock.patch.object(
            setup_module, "setup_chart_of_accounts"
        ), unittest.mock.patch.object(
            setup_module, "map_gl_account"
        ) as mock_map, unittest.mock.patch.object(
            setup_module, "_map_component_to_account"
        ) as mock_comp_map, unittest.mock.patch.object(
            setup_module, "get_gl_account_for_salary_component", return_value="ACC"
        ):
            result = setup_module.setup_company_accounts(company=self.company, config=config)

        self.assertTrue(result)
        called_keys = [call.args[1] for call in mock_map.call_args_list]
        for key in expected_keys:
            self.assertIn(key, called_keys)
        self.assertEqual(len(called_keys), len(expected_keys))

        called_components = [call.args[0] for call in mock_comp_map.call_args_list]
        for comp in salary_components:
            self.assertIn(comp, called_components)
        self.assertEqual(len(called_components), len(salary_components))
