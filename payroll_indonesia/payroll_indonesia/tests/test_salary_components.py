# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.utils import flt, getdate
from payroll_indonesia.override.salary_slip.salary_slip_functions import update_component_amount


class TestSalaryComponents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test environment"""
        cls.setup_test_employee()
        cls.setup_salary_components()

    @classmethod
    def tearDownClass(cls):
        """Clean up test data"""
        frappe.db.rollback()

    @classmethod
    def setup_test_employee(cls):
        """Create test employee"""
        if frappe.db.exists("Employee", "SC-TEST-EMP"):
            return frappe.get_doc("Employee", "SC-TEST-EMP")

        employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "employee_name": "Salary Component Test",
                "first_name": "Salary",
                "last_name": "Component Test",
                "name": "SC-TEST-EMP",
                "status": "Active",
                "company": frappe.defaults.get_user_default("Company"),
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2024-01-01",
                "department": "All Departments",
                "gender": "Male",
            }
        )
        employee.insert(ignore_permissions=True)
        cls.test_employee = employee

    @classmethod
    def setup_salary_components(cls):
        """Create test salary components if they don't exist"""
        components = [
            {"name": "Basic Salary", "type": "earnings", "abbr": "BS"},
            {"name": "PPh 21", "type": "deductions", "abbr": "PPH"},
            {"name": "Transport Allowance", "type": "earnings", "abbr": "TA"},
            {"name": "BPJS TK", "type": "deductions", "abbr": "BPJS"},
        ]

        for comp in components:
            if not frappe.db.exists("Salary Component", comp["name"]):
                doc = frappe.get_doc(
                    {
                        "doctype": "Salary Component",
                        "salary_component": comp["name"],
                        "salary_component_abbr": comp["abbr"],
                        "type": comp["type"],
                    }
                )
                doc.insert(ignore_permissions=True)

    def create_test_salary_slip(self, with_components=True):
        """Create a test salary slip with optional initial components"""
        salary_slip = frappe.get_doc(
            {
                "doctype": "Salary Slip",
                "employee": self.test_employee.name,
                "start_date": getdate(),
                "end_date": getdate(),
                "posting_date": getdate(),
                "company": frappe.defaults.get_user_default("Company"),
            }
        )

        if with_components:
            # Add some initial components
            salary_slip.earnings = [
                {"salary_component": "Basic Salary", "amount": 5000000},
                {"salary_component": "Transport Allowance", "amount": 500000},
            ]

            salary_slip.deductions = [{"salary_component": "BPJS TK", "amount": 100000}]

        salary_slip.insert(ignore_permissions=True)
        return salary_slip

    def test_add_new_component(self):
        """Test adding a new component"""
        salary_slip = self.create_test_salary_slip(with_components=False)

        # Add PPh 21 component
        update_component_amount(salary_slip, "PPh 21", 350000, "deductions")

        # Verify component was added
        pph21_found = False
        for d in salary_slip.deductions:
            if d.salary_component == "PPh 21":
                pph21_found = True
                self.assertEqual(flt(d.amount, 2), 350000)
                break

        self.assertTrue(pph21_found, "PPh 21 component not added")

    def test_update_existing_component(self):
        """Test updating an existing component"""
        salary_slip = self.create_test_salary_slip()

        # Update existing BPJS TK amount
        new_amount = 150000
        update_component_amount(salary_slip, "BPJS TK", new_amount, "deductions")

        # Verify amount was updated
        for d in salary_slip.deductions:
            if d.salary_component == "BPJS TK":
                self.assertEqual(flt(d.amount, 2), new_amount)
                break

    def test_remove_component_with_zero(self):
        """Test removing component by setting amount to zero"""
        salary_slip = self.create_test_salary_slip()

        # Set BPJS TK amount to zero
        update_component_amount(salary_slip, "BPJS TK", 0, "deductions")

        # Verify component was removed
        bpjs_found = False
        for d in salary_slip.deductions:
            if d.salary_component == "BPJS TK":
                bpjs_found = True
                break

        self.assertFalse(bpjs_found, "Component not removed when amount set to zero")

    def test_add_to_different_component_types(self):
        """Test adding components to both earnings and deductions"""
        salary_slip = self.create_test_salary_slip(with_components=False)

        # Add an earning
        update_component_amount(salary_slip, "Transport Allowance", 500000, "earnings")

        # Add a deduction
        update_component_amount(salary_slip, "PPh 21", 350000, "deductions")

        # Verify both were added correctly
        transport_found = False
        pph21_found = False

        for e in salary_slip.earnings:
            if e.salary_component == "Transport Allowance":
                transport_found = True
                self.assertEqual(flt(e.amount, 2), 500000)

        for d in salary_slip.deductions:
            if d.salary_component == "PPh 21":
                pph21_found = True
                self.assertEqual(flt(d.amount, 2), 350000)

        self.assertTrue(transport_found, "Earning component not added")
        self.assertTrue(pph21_found, "Deduction component not added")

    def test_update_invalid_component(self):
        """Test handling of invalid component name"""
        salary_slip = self.create_test_salary_slip()

        # Try to update non-existent component
        with self.assertRaises(frappe.ValidationError):
            update_component_amount(salary_slip, "Invalid Component", 1000, "earnings")

    def test_update_wrong_component_type(self):
        """Test handling of wrong component type"""
        salary_slip = self.create_test_salary_slip()

        # Try to add deduction component to earnings
        with self.assertRaises(frappe.ValidationError):
            update_component_amount(salary_slip, "PPh 21", 350000, "earnings")

        # Try to add earning component to deductions
        with self.assertRaises(frappe.ValidationError):
            update_component_amount(salary_slip, "Transport Allowance", 500000, "deductions")

    def test_multiple_updates(self):
        """Test multiple updates to same component"""
        salary_slip = self.create_test_salary_slip()

        # Update BPJS TK amount multiple times
        amounts = [150000, 200000, 250000]

        for amount in amounts:
            update_component_amount(salary_slip, "BPJS TK", amount, "deductions")

            # Verify amount was updated
            component_found = False
            for d in salary_slip.deductions:
                if d.salary_component == "BPJS TK":
                    component_found = True
                    self.assertEqual(flt(d.amount, 2), amount)
                    break

            self.assertTrue(component_found, f"Component not found after update to {amount}")

    def test_zero_then_nonzero(self):
        """Test removing then re-adding component"""
        salary_slip = self.create_test_salary_slip()

        # Remove BPJS TK by setting to zero
        update_component_amount(salary_slip, "BPJS TK", 0, "deductions")

        # Verify removal
        bpjs_found = False
        for d in salary_slip.deductions:
            if d.salary_component == "BPJS TK":
                bpjs_found = True
                break
        self.assertFalse(bpjs_found, "Component not removed")

        # Re-add BPJS TK
        new_amount = 150000
        update_component_amount(salary_slip, "BPJS TK", new_amount, "deductions")

        # Verify re-addition
        bpjs_found = False
        for d in salary_slip.deductions:
            if d.salary_component == "BPJS TK":
                bpjs_found = True
                self.assertEqual(flt(d.amount, 2), new_amount)
                break
        self.assertTrue(bpjs_found, "Component not re-added")


def run_salary_component_tests():
    """Run salary component tests"""
    import frappe.test_runner

    test_result = frappe.test_runner.run_tests(
        {
            "tests": [
                {
                    "module_name": "payroll_indonesia.payroll_indonesia.tests.test_salary_components",
                    "test_name": "TestSalaryComponents",
                }
            ]
        }
    )
    return test_result
