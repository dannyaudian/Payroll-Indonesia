# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.utils import flt, getdate, add_months
from payroll_indonesia.override.salary_slip.ter_calculator import (
    calculate_monthly_pph_with_ter,
    get_ptkp_category,
)


class TestTERCalculator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test data"""
        cls.setup_test_employee()
        cls.setup_test_salary_slip()

    @classmethod
    def tearDownClass(cls):
        """Clean up test data"""
        frappe.db.rollback()

    @classmethod
    def setup_test_employee(cls):
        """Create test employee with required fields"""
        employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "Test",
                "last_name": "Employee TER",
                "status": "Active",
                "company": frappe.defaults.get_user_default("Company"),
                "date_of_birth": add_months(getdate(), -(25 * 12)),  # 25 years old
                "date_of_joining": add_months(getdate(), -12),
                "department": "All Departments",
                "gender": "Male",
                # Indonesian Payroll fields
                "status_pajak": "TK0",
                "npwp": "123456789012345",
                "override_tax_method": "TER",
            }
        )
        employee.insert(ignore_permissions=True)
        cls.test_employee = employee

    @classmethod
    def setup_test_salary_slip(cls):
        """Create test salary slip"""
        salary_slip = frappe.get_doc(
            {
                "doctype": "Salary Slip",
                "employee": cls.test_employee.name,
                "start_date": getdate(),
                "end_date": getdate(),
                "posting_date": getdate(),
                "company": frappe.defaults.get_user_default("Company"),
                # TER specific fields
                "is_using_ter": 1,
                "gross_pay": 10000000,  # 10 juta rupiah
            }
        )
        salary_slip.insert(ignore_permissions=True)
        cls.test_salary_slip = salary_slip

    def test_ter_calculation_basic(self):
        """Test basic TER calculation for TK0 with NPWP"""
        calculate_monthly_pph_with_ter(self.test_salary_slip, self.test_employee)

        # Assert TER calculation results
        self.assertEqual(self.test_salary_slip.ter_category, "A")  # For income < 13jt
        self.assertEqual(flt(self.test_salary_slip.ter_rate, 2), 5.00)  # 5% for Category A

        # Verify salary slip fields are updated
        self.assertEqual(self.test_salary_slip.ter_category, "A")
        self.assertEqual(flt(self.test_salary_slip.ter_rate, 2), 5.00)
        self.assertEqual(
            flt(self.test_salary_slip.monthly_tax), flt(self.test_salary_slip.gross_pay * 0.05)
        )

    def test_ter_calculation_no_npwp(self):
        """Test TER calculation for employee without NPWP (120% penalty)"""
        self.test_employee.npwp = ""
        self.test_employee.save()

        calculate_monthly_pph_with_ter(self.test_salary_slip, self.test_employee)

        base_tax = self.test_salary_slip.gross_pay * 0.05
        expected_tax = base_tax * 1.2  # 120% penalty

        self.assertEqual(flt(self.test_salary_slip.monthly_tax), flt(expected_tax))

        # Restore NPWP
        self.test_employee.npwp = "123456789012345"
        self.test_employee.save()

    def test_ter_calculation_high_income(self):
        """Test TER calculation for high income (Category C)"""
        self.test_salary_slip.gross_pay = 35000000  # 35 juta rupiah
        self.test_salary_slip.save()

        calculate_monthly_pph_with_ter(self.test_salary_slip, self.test_employee)

        self.assertEqual(self.test_salary_slip.ter_category, "C")  # For income > 32jt
        self.assertEqual(flt(self.test_salary_slip.ter_rate, 2), 15.00)  # 15% for Category C

    def test_ter_annual_projection(self):
        """Test annual taxable amount projection"""
        self.test_salary_slip.gross_pay = 20000000  # 20 juta rupiah
        self.test_salary_slip.save()

        calculate_monthly_pph_with_ter(self.test_salary_slip, self.test_employee)

        expected_annual = self.test_salary_slip.gross_pay * 12
        self.assertEqual(flt(self.test_salary_slip.annual_taxable_income), flt(expected_annual))

    def test_invalid_tax_status(self):
        """Test handling of invalid tax status"""
        self.test_employee.status_pajak = "INVALID"
        self.test_employee.save()

        with self.assertRaises(frappe.ValidationError):
            calculate_monthly_pph_with_ter(self.test_salary_slip, self.test_employee)

        # Restore valid status
        self.test_employee.status_pajak = "TK0"
        self.test_employee.save()

    def test_ptkp_mapping(self):
        """Test PTKP category mapping for different tax statuses"""
        test_cases = [
            ("TK0", "A"),  # Single, no dependents
            ("K2", "B"),  # Married, 2 dependents
            ("HB3", "C"),  # Widow/Widower, 3 dependents
        ]

        for status, expected_category in test_cases:
            self.test_employee.status_pajak = status
            self.test_employee.save()

            category = get_ptkp_category(self.test_employee)
            self.assertEqual(
                category, expected_category, f"Failed PTKP mapping for status {status}"
            )

    def test_zero_income(self):
        """Test handling of zero income"""
        self.test_salary_slip.gross_pay = 0
        self.test_salary_slip.save()

        calculate_monthly_pph_with_ter(self.test_salary_slip, self.test_employee)

        self.assertEqual(flt(self.test_salary_slip.monthly_tax), 0)


def run_ter_calculator_tests():
    """Run TER calculator tests"""
    import frappe.test_runner

    test_result = frappe.test_runner.run_tests(
        {
            "tests": [
                {
                    "module_name": "payroll_indonesia.payroll_indonesia.tests.test_ter_calculator",
                    "test_name": "TestTERCalculator",
                }
            ]
        }
    )
    return test_result
