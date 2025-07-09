# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import pytest

frappe = pytest.importorskip("frappe")
from payroll_indonesia import utils


class TestUpdateEmployeeTaxSummary(unittest.TestCase):
    @patch(
        "payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.create_from_salary_slip"
    )
    def test_calls_create_from_salary_slip(self, mock_create):
        mock_create.return_value = "TAX-001"
        result = utils.update_employee_tax_summary("EMP-001", "SS-001")
        mock_create.assert_called_once_with("SS-001")
        self.assertEqual(result, "TAX-001")

    @patch("payroll_indonesia.utils.logger")
    @patch(
        "payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.create_from_salary_slip"
    )
    def test_logs_error_when_exception(self, mock_create, mock_logger):
        mock_create.side_effect = Exception("boom")
        result = utils.update_employee_tax_summary("EMP-001", "SS-001")
        mock_create.assert_called_once_with("SS-001")
        self.assertIsNone(result)
        self.assertTrue(mock_logger.error.called)


if __name__ == "__main__":
    unittest.main()
