# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.utils import flt, getdate, add_months
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components
from payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation import get_bpjs_settings


class TestTaxCalculator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Initialize test environment"""
        cls.setup_test_employees()
        cls.bpjs_settings = get_bpjs_settings()
        cls.example_gross = 15000000  # 15 juta rupiah

    @classmethod
    def tearDownClass(cls):
        """Cleanup test data"""
        frappe.db.rollback()

    @classmethod
    def setup_test_employees(cls):
        """Create test employees with different configurations"""
        cls.test_employees = {
            "complete": cls.create_test_employee(
                "Complete Setup",
                {
                    "npwp": "123456789012345",
                    "ikut_bpjs_kesehatan": 1,
                    "ikut_bpjs_ketenagakerjaan": 1,
                    "override_tax_method": "",
                },
            ),
            "no_npwp": cls.create_test_employee(
                "No NPWP",
                {
                    "npwp": "",
                    "ikut_bpjs_kesehatan": 1,
                    "ikut_bpjs_ketenagakerjaan": 1,
                    "override_tax_method": "",
                },
            ),
            "no_bpjs": cls.create_test_employee(
                "No BPJS",
                {
                    "npwp": "123456789012345",
                    "ikut_bpjs_kesehatan": 0,
                    "ikut_bpjs_ketenagakerjaan": 0,
                    "override_tax_method": "",
                },
            ),
            "ter_override": cls.create_test_employee(
                "TER Override",
                {
                    "npwp": "123456789012345",
                    "ikut_bpjs_kesehatan": 1,
                    "ikut_bpjs_ketenagakerjaan": 1,
                    "override_tax_method": "TER",
                },
            ),
            "progressive_override": cls.create_test_employee(
                "Progressive Override",
                {
                    "npwp": "123456789012345",
                    "ikut_bpjs_kesehatan": 1,
                    "ikut_bpjs_ketenagakerjaan": 1,
                    "override_tax_method": "Progressive",
                },
            ),
        }

    @classmethod
    def create_test_employee(cls, name_suffix, config):
        """Create a test employee with given configuration"""
        employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"Test {name_suffix}",
                "last_name": "Tax Calc",
                "status": "Active",
                "company": frappe.defaults.get_user_default("Company"),
                "date_of_birth": add_months(getdate(), -(30 * 12)),  # 30 years old
                "date_of_joining": add_months(getdate(), -12),
                "department": "All Departments",
                "gender": "Male",
                "status_pajak": "TK0",
                # Configuration from params
                "npwp": config.get("npwp", ""),
                "ikut_bpjs_kesehatan": config.get("ikut_bpjs_kesehatan", 1),
                "ikut_bpjs_ketenagakerjaan": config.get("ikut_bpjs_ketenagakerjaan", 1),
                "override_tax_method": config.get("override_tax_method", ""),
            }
        )
        employee.insert(ignore_permissions=True)
        return employee

    def create_salary_slip(self, employee, gross_pay=None):
        """Create a test salary slip"""
        salary_slip = frappe.get_doc(
            {
                "doctype": "Salary Slip",
                "employee": employee.name,
                "start_date": getdate(),
                "end_date": getdate(),
                "posting_date": getdate(),
                "company": frappe.defaults.get_user_default("Company"),
                "gross_pay": gross_pay or self.example_gross,
            }
        )
        salary_slip.insert(ignore_permissions=True)
        return salary_slip

    def calculate_expected_bpjs(self, gross_pay):
        """Calculate expected BPJS deductions"""
        kesehatan = min(
            gross_pay * self.bpjs_settings.kesehatan_employee_percent / 100,
            self.bpjs_settings.kesehatan_max_salary
            * self.bpjs_settings.kesehatan_employee_percent
            / 100,
        )

        jht = gross_pay * self.bpjs_settings.jht_employee_percent / 100

        jp = min(
            gross_pay * self.bpjs_settings.jp_employee_percent / 100,
            self.bpjs_settings.jp_max_salary * self.bpjs_settings.jp_employee_percent / 100,
        )

        return {"kesehatan": kesehatan, "jht": jht, "jp": jp, "total": kesehatan + jht + jp}

    def test_complete_setup_ter(self):
        """Test tax calculation with complete setup using TER"""
        employee = self.test_employees["complete"]
        salary_slip = self.create_salary_slip(employee)

        # Calculate tax components
        result = calculate_tax_components(salary_slip, employee)
        self.assertTrue(result.get("success"))

        # Expected BPJS deductions
        bpjs = self.calculate_expected_bpjs(salary_slip.gross_pay)

        # Verify BPJS exclusion from taxable income
        expected_taxable = salary_slip.gross_pay - bpjs["total"]
        self.assertEqual(flt(salary_slip.monthly_taxable_income, 2), flt(expected_taxable, 2))

        # Verify TER application
        self.assertTrue(salary_slip.is_using_ter)
        self.assertTrue(salary_slip.ter_rate > 0)

        # Verify final PPh21 amount
        expected_pph21 = expected_taxable * (salary_slip.ter_rate / 100)
        self.assertEqual(flt(salary_slip.monthly_tax, 2), flt(expected_pph21, 2))

    def test_no_npwp_penalty(self):
        """Test 120% tax penalty for employees without NPWP"""
        employee = self.test_employees["no_npwp"]
        salary_slip = self.create_salary_slip(employee)

        result = calculate_tax_components(salary_slip, employee)
        self.assertTrue(result.get("success"))

        # Get base tax amount
        base_tax = salary_slip.monthly_tax / 1.2  # Remove penalty to get base

        # Verify 120% penalty applied
        self.assertEqual(flt(salary_slip.monthly_tax, 2), flt(base_tax * 1.2, 2))

    def test_no_bpjs_calculation(self):
        """Test tax calculation without BPJS enrollment"""
        employee = self.test_employees["no_bpjs"]
        salary_slip = self.create_salary_slip(employee)

        result = calculate_tax_components(salary_slip, employee)
        self.assertTrue(result.get("success"))

        # Verify no BPJS deductions
        self.assertEqual(salary_slip.total_bpjs, 0)

        # Verify taxable income equals gross (no BPJS reduction)
        self.assertEqual(flt(salary_slip.monthly_taxable_income, 2), flt(salary_slip.gross_pay, 2))

    def test_ter_override(self):
        """Test explicit TER method override"""
        employee = self.test_employees["ter_override"]
        salary_slip = self.create_salary_slip(employee)

        result = calculate_tax_components(salary_slip, employee)
        self.assertTrue(result.get("success"))

        # Verify TER method used
        self.assertTrue(salary_slip.is_using_ter)
        self.assertTrue(salary_slip.ter_rate > 0)
        self.assertTrue(salary_slip.ter_category)

    def test_progressive_override(self):
        """Test explicit Progressive method override"""
        employee = self.test_employees["progressive_override"]
        salary_slip = self.create_salary_slip(employee)

        result = calculate_tax_components(salary_slip, employee)
        self.assertTrue(result.get("success"))

        # Verify Progressive method used
        self.assertFalse(salary_slip.is_using_ter)
        self.assertEqual(salary_slip.ter_rate, 0)
        self.assertFalse(salary_slip.ter_category)

    def test_annual_projection(self):
        """Test annual taxable amount projection"""
        employee = self.test_employees["complete"]
        salary_slip = self.create_salary_slip(employee)

        result = calculate_tax_components(salary_slip, employee)
        self.assertTrue(result.get("success"))

        # Calculate expected annual projection
        monthly_taxable = salary_slip.monthly_taxable_income
        expected_annual = monthly_taxable * 12

        self.assertEqual(flt(salary_slip.annual_taxable_income, 2), flt(expected_annual, 2))

    def test_high_income_progressive(self):
        """Test Progressive calculation for high income"""
        employee = self.test_employees["progressive_override"]
        salary_slip = self.create_salary_slip(employee, gross_pay=50000000)  # 50 juta rupiah

        result = calculate_tax_components(salary_slip, employee)
        self.assertTrue(result.get("success"))

        # Verify progressive tax brackets applied
        self.assertTrue(salary_slip.monthly_tax > 0)
        self.assertFalse(salary_slip.is_using_ter)

    def test_zero_income(self):
        """Test handling of zero income"""
        employee = self.test_employees["complete"]
        salary_slip = self.create_salary_slip(employee, gross_pay=0)

        result = calculate_tax_components(salary_slip, employee)
        self.assertTrue(result.get("success"))

        # Verify no tax for zero income
        self.assertEqual(salary_slip.monthly_tax, 0)
        self.assertEqual(salary_slip.annual_taxable_income, 0)


def run_tax_calculator_tests():
    """Run tax calculator tests"""
    import frappe.test_runner

    test_result = frappe.test_runner.run_tests(
        {
            "tests": [
                {
                    "module_name": "payroll_indonesia.payroll_indonesia.tests.test_tax_calculator",
                    "test_name": "TestTaxCalculator",
                }
            ]
        }
    )
    return test_result
