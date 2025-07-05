# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.utils import getdate, add_months, get_first_day, get_last_day, flt, add_days
from payroll_indonesia.override.salary_slip.tax_calculator import calculate_tax_components

# from payroll_indonesia.override.salary_slip.ter_calculator import calculate_monthly_pph_with_ter
# from payroll_indonesia.override.salary_slip.gl_entry_override import make_gl_entries


class TestPayrollIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Setup test environment"""
        cls.setup_company()
        cls.setup_test_employees()
        cls.setup_salary_structure()
        cls.setup_salary_structure_assignments()

    @classmethod
    def tearDownClass(cls):
        """Cleanup test data"""
        frappe.db.rollback()

    @classmethod
    def setup_company(cls):
        """Setup test company with required accounts"""
        cls.company = frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": "Test Payroll Company",
                "country": "Indonesia",
                "default_currency": "IDR",
                "abbr": "TPC",
                "domain": "Manufacturing",
            }
        )

        if not frappe.db.exists("Company", cls.company.name):
            cls.company.insert()

        # Setup accounts
        accounts = [
            {"account_name": "BPJS Payable", "account_type": "Payable"},
            {"account_name": "PPh 21 Payable", "account_type": "Payable"},
            {"account_name": "Payroll Payable", "account_type": "Payable"},
            {"account_name": "Salary", "account_type": "Expense"},
        ]

        for acc in accounts:
            if not frappe.db.exists("Account", f"{acc['account_name']} - {cls.company.abbr}"):
                account = frappe.get_doc(
                    {
                        "doctype": "Account",
                        "account_name": acc["account_name"],
                        "parent_account": (
                            f"Accounts Payable - {cls.company.abbr}"
                            if acc["account_type"] == "Payable"
                            else f"Expenses - {cls.company.abbr}"
                        ),
                        "account_type": acc["account_type"],
                        "company": cls.company.name,
                    }
                )
                account.insert()

        # Set default accounts
        cls.company.default_payroll_payable_account = f"Payroll Payable - {cls.company.abbr}"
        cls.company.default_bpjs_payable_account = f"BPJS Payable - {cls.company.abbr}"
        cls.company.default_pph21_payable_account = f"PPh 21 Payable - {cls.company.abbr}"
        cls.company.save()

    @classmethod
    def setup_test_employees(cls):
        """Create test employees with different configurations"""
        cls.test_employees = {
            "ter_with_bpjs": cls.create_test_employee(
                "TER with BPJS",
                {
                    "status_pajak": "K0",
                    "override_tax_method": "TER",
                    "ikut_bpjs_kesehatan": 1,
                    "ikut_bpjs_ketenagakerjaan": 1,
                },
            ),
            "progressive_with_bpjs": cls.create_test_employee(
                "Progressive with BPJS",
                {
                    "status_pajak": "K0",
                    "override_tax_method": "Progressive",
                    "ikut_bpjs_kesehatan": 1,
                    "ikut_bpjs_ketenagakerjaan": 1,
                },
            ),
            "ter_no_bpjs": cls.create_test_employee(
                "TER no BPJS",
                {
                    "status_pajak": "K0",
                    "override_tax_method": "TER",
                    "ikut_bpjs_kesehatan": 0,
                    "ikut_bpjs_ketenagakerjaan": 0,
                },
            ),
        }

    @classmethod
    def create_test_employee(cls, name_suffix, config):
        """Create test employee with given configuration"""
        employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": f"Test {name_suffix}",
                "last_name": "Employee",
                "status": "Active",
                "company": cls.company.name,
                "date_of_birth": add_months(getdate(), -(30 * 12)),  # 30 years old
                "date_of_joining": add_months(getdate(), -12),
                "department": "All Departments",
                "employment_type": "Permanent",
                "gender": "Male",
                "npwp": "123456789012345",
                # Configuration from params
                "status_pajak": config.get("status_pajak", "TK0"),
                "override_tax_method": config.get("override_tax_method", ""),
                "ikut_bpjs_kesehatan": config.get("ikut_bpjs_kesehatan", 1),
                "ikut_bpjs_ketenagakerjaan": config.get("ikut_bpjs_ketenagakerjaan", 1),
            }
        )
        employee.insert()
        return employee

    @classmethod
    def setup_salary_structure(cls):
        """Create necessary salary structures for testing"""
        # First, create the required salary components if they don't exist
        components = [
            {"doctype": "Salary Component", "salary_component": "Basic Salary", "type": "Earning"},
            {
                "doctype": "Salary Component",
                "salary_component": "BPJS Kesehatan",
                "type": "Deduction",
            },
            {"doctype": "Salary Component", "salary_component": "BPJS JHT", "type": "Deduction"},
            {"doctype": "Salary Component", "salary_component": "BPJS JP", "type": "Deduction"},
            {"doctype": "Salary Component", "salary_component": "PPh 21", "type": "Deduction"},
        ]

        for component in components:
            if not frappe.db.exists("Salary Component", component["salary_component"]):
                frappe.get_doc(component).insert()

        # Create a test salary structure with the above components
        if not frappe.db.exists("Salary Structure", "Test Payroll Indonesia Structure"):
            salary_structure = frappe.get_doc(
                {
                    "doctype": "Salary Structure",
                    "name": "Test Payroll Indonesia Structure",
                    "company": cls.company.name,
                    "is_active": "Yes",
                    "payroll_frequency": "Monthly",
                    "payment_account": f"Cash - {cls.company.abbr}",
                }
            )

            # Add earnings
            salary_structure.append(
                "earnings",
                {
                    "salary_component": "Basic Salary",
                    "abbr": "BS",
                    "amount_based_on_formula": 0,
                    "formula": "",
                    "amount": 15000000,  # 15 juta
                },
            )

            # Add deductions
            salary_structure.append(
                "deductions",
                {
                    "salary_component": "BPJS Kesehatan",
                    "abbr": "BKE",
                    "amount_based_on_formula": 1,
                    "formula": "gross_pay * 0.01",  # 1% of gross pay
                    "amount": 0,
                },
            )

            salary_structure.append(
                "deductions",
                {
                    "salary_component": "BPJS JHT",
                    "abbr": "BJH",
                    "amount_based_on_formula": 1,
                    "formula": "gross_pay * 0.02",  # 2% of gross pay
                    "amount": 0,
                },
            )

            salary_structure.append(
                "deductions",
                {
                    "salary_component": "BPJS JP",
                    "abbr": "BJP",
                    "amount_based_on_formula": 1,
                    "formula": "gross_pay * 0.01",  # 1% of gross pay
                    "amount": 0,
                },
            )

            salary_structure.append(
                "deductions",
                {
                    "salary_component": "PPh 21",
                    "abbr": "PPh",
                    "amount_based_on_formula": 0,  # Will be calculated by our tax module
                    "formula": "",
                    "amount": 0,
                },
            )

            # Insert the salary structure
            salary_structure.insert()

    @classmethod
    def setup_salary_structure_assignments(cls):
        """Assign salary structures to employees"""
        # Get the earliest date needed for tests - we'll use 1st of previous year to ensure coverage
        earliest_date = add_days(get_first_day(add_months(getdate(), -12)), -1)

        # Create assignments for each test employee
        for employee_key, employee in cls.test_employees.items():
            # Check if assignment already exists
            existing_assignment = frappe.db.exists(
                "Salary Structure Assignment",
                {"employee": employee.name, "salary_structure": "Test Payroll Indonesia Structure"},
            )

            if not existing_assignment:
                assignment = frappe.get_doc(
                    {
                        "doctype": "Salary Structure Assignment",
                        "employee": employee.name,
                        "salary_structure": "Test Payroll Indonesia Structure",
                        "from_date": earliest_date,
                        "base": 15000000,  # Base salary matches earnings component
                        "company": cls.company.name,
                    }
                )
                assignment.insert()

    def create_payroll_entry(self, posting_date):
        """Create test payroll entry"""
        start_date = get_first_day(posting_date)
        end_date = get_last_day(posting_date)

        payroll_entry = frappe.get_doc(
            {
                "doctype": "Payroll Entry",
                "company": self.company.name,
                "posting_date": posting_date,
                "payroll_frequency": "Monthly",
                "start_date": start_date,
                "end_date": end_date,
                "payment_account": f"Cash - {self.company.abbr}",
            }
        )

        # Add employees
        for employee in self.test_employees.values():
            payroll_entry.append(
                "employees", {"employee": employee.name, "base_gross_pay": 15000000}  # 15 juta
            )

        payroll_entry.insert()
        return payroll_entry

    def test_ter_with_bpjs_december(self):
        """Test TER calculation with BPJS in December"""
        # Create December payroll entry
        december_date = getdate("2025-12-15")
        payroll_entry = self.create_payroll_entry(december_date)

        # Create salary slip
        salary_slip = frappe.get_doc(
            {
                "doctype": "Salary Slip",
                "employee": self.test_employees["ter_with_bpjs"].name,
                "posting_date": december_date,
                "start_date": get_first_day(december_date),
                "end_date": get_last_day(december_date),
                "company": self.company.name,
                "payroll_entry": payroll_entry.name,
            }
        )

        # Set test earnings
        salary_slip.append("earnings", {"salary_component": "Basic Salary", "amount": 15000000})

        salary_slip.gross_pay = 15000000
        salary_slip.insert()

        # Calculate tax components
        calculate_tax_components(salary_slip, self.test_employees["ter_with_bpjs"])

        # Verify TER calculation
        self.assertTrue(hasattr(salary_slip, "is_using_ter"), "is_using_ter attribute is missing")
        self.assertTrue(hasattr(salary_slip, "ter_rate"), "ter_rate attribute is missing")
        self.assertTrue(salary_slip.ter_rate > 0, "ter_rate should be greater than 0")
        self.assertTrue(hasattr(salary_slip, "ter_category"), "ter_category attribute is missing")

        # Verify BPJS deductions exist
        bpjs_components = ["BPJS Kesehatan", "BPJS JHT", "BPJS JP"]
        for component in bpjs_components:
            deduction = next(
                (d for d in salary_slip.deductions if d.salary_component == component), None
            )
            self.assertIsNotNone(deduction, f"{component} deduction is missing")
            self.assertTrue(deduction.amount > 0, f"{component} amount should be greater than 0")

        # Verify PPh 21 deduction
        pph21_deduction = next(
            (d for d in salary_slip.deductions if d.salary_component == "PPh 21"), None
        )
        self.assertIsNotNone(pph21_deduction, "PPh 21 deduction is missing")
        self.assertTrue(pph21_deduction.amount > 0, "PPh 21 amount should be greater than 0")

        # Verify December correction exists
        self.assertTrue(hasattr(salary_slip, "koreksi_pph21"), "koreksi_pph21 attribute is missing")
        self.assertTrue(salary_slip.koreksi_pph21 > 0, "koreksi_pph21 should be greater than 0")

        # Submit salary slip
        salary_slip.submit()

        # Get GL entries
        gl_entries = frappe.get_all(
            "GL Entry",
            filters={"voucher_no": salary_slip.name},
            fields=["account", "debit", "credit"],
        )

        # Verify GL entries
        required_accounts = [
            f"BPJS Payable - {self.company.abbr}",
            f"PPh 21 Payable - {self.company.abbr}",
            f"Payroll Payable - {self.company.abbr}",
            f"Salary - {self.company.abbr}",
        ]

        for account in required_accounts:
            entry = next((e for e in gl_entries if e.account == account), None)
            self.assertIsNotNone(entry, f"Missing GL entry for {account}")

        # Verify total debit equals total credit
        total_debit = sum(flt(e.debit) for e in gl_entries)
        total_credit = sum(flt(e.credit) for e in gl_entries)
        self.assertEqual(flt(total_debit, 2), flt(total_credit, 2))

    def test_progressive_with_bpjs_regular(self):
        """Test Progressive calculation with BPJS in regular month"""
        # Create regular month payroll entry (e.g. May)
        may_date = getdate("2025-05-15")
        payroll_entry = self.create_payroll_entry(may_date)

        # Create salary slip
        salary_slip = frappe.get_doc(
            {
                "doctype": "Salary Slip",
                "employee": self.test_employees["progressive_with_bpjs"].name,
                "posting_date": may_date,
                "start_date": get_first_day(may_date),
                "end_date": get_last_day(may_date),
                "company": self.company.name,
                "payroll_entry": payroll_entry.name,
            }
        )

        # Set test earnings
        salary_slip.append("earnings", {"salary_component": "Basic Salary", "amount": 15000000})

        salary_slip.gross_pay = 15000000
        salary_slip.insert()

        # Calculate tax components
        calculate_tax_components(salary_slip, self.test_employees["progressive_with_bpjs"])

        # Verify Progressive calculation
        self.assertTrue(hasattr(salary_slip, "is_using_ter"), "is_using_ter attribute is missing")
        self.assertFalse(
            salary_slip.is_using_ter, "is_using_ter should be False for progressive calculation"
        )
        self.assertTrue(hasattr(salary_slip, "ter_rate"), "ter_rate attribute is missing")
        self.assertEqual(
            salary_slip.ter_rate, 0, "ter_rate should be 0 for progressive calculation"
        )

        # Verify BPJS deductions
        bpjs_components = ["BPJS Kesehatan", "BPJS JHT", "BPJS JP"]
        for component in bpjs_components:
            deduction = next(
                (d for d in salary_slip.deductions if d.salary_component == component), None
            )
            self.assertIsNotNone(deduction, f"{component} deduction is missing")
            self.assertTrue(deduction.amount > 0, f"{component} amount should be greater than 0")

        # Verify PPh 21 deduction
        pph21_deduction = next(
            (d for d in salary_slip.deductions if d.salary_component == "PPh 21"), None
        )
        self.assertIsNotNone(pph21_deduction, "PPh 21 deduction is missing")
        self.assertTrue(pph21_deduction.amount > 0, "PPh 21 amount should be greater than 0")

        # Verify no December correction in regular month
        self.assertTrue(hasattr(salary_slip, "koreksi_pph21"), "koreksi_pph21 attribute is missing")
        self.assertEqual(
            salary_slip.koreksi_pph21, 0, "koreksi_pph21 should be 0 in a regular month"
        )

        # Submit salary slip
        salary_slip.submit()

        # Verify GL entries
        gl_entries = frappe.get_all(
            "GL Entry",
            filters={"voucher_no": salary_slip.name},
            fields=["account", "debit", "credit"],
        )

        # Verify GL entries balance
        total_debit = sum(flt(e.debit) for e in gl_entries)
        total_credit = sum(flt(e.credit) for e in gl_entries)
        self.assertEqual(flt(total_debit, 2), flt(total_credit, 2))

    def test_ter_without_bpjs(self):
        """Test TER calculation without BPJS enrollment"""
        # Create regular month payroll entry
        test_date = getdate("2025-05-15")
        payroll_entry = self.create_payroll_entry(test_date)

        # Create salary slip
        salary_slip = frappe.get_doc(
            {
                "doctype": "Salary Slip",
                "employee": self.test_employees["ter_no_bpjs"].name,
                "posting_date": test_date,
                "start_date": get_first_day(test_date),
                "end_date": get_last_day(test_date),
                "company": self.company.name,
                "payroll_entry": payroll_entry.name,
            }
        )

        # Set test earnings
        salary_slip.append("earnings", {"salary_component": "Basic Salary", "amount": 15000000})

        salary_slip.gross_pay = 15000000
        salary_slip.insert()

        # Calculate tax components
        calculate_tax_components(salary_slip, self.test_employees["ter_no_bpjs"])

        # Verify TER calculation
        self.assertTrue(hasattr(salary_slip, "is_using_ter"), "is_using_ter attribute is missing")
        self.assertTrue(salary_slip.is_using_ter, "is_using_ter should be True")
        self.assertTrue(hasattr(salary_slip, "ter_rate"), "ter_rate attribute is missing")
        self.assertTrue(salary_slip.ter_rate > 0, "ter_rate should be greater than 0")

        # Verify no BPJS deductions
        bpjs_components = ["BPJS Kesehatan", "BPJS JHT", "BPJS JP"]
        for component in bpjs_components:
            deduction = next(
                (d for d in salary_slip.deductions if d.salary_component == component), None
            )
            self.assertIsNone(deduction, f"{component} should not be present when BPJS is disabled")

        # Verify PPh 21 is still calculated
        pph21_deduction = next(
            (d for d in salary_slip.deductions if d.salary_component == "PPh 21"), None
        )
        self.assertIsNotNone(pph21_deduction, "PPh 21 deduction is missing")
        self.assertTrue(pph21_deduction.amount > 0, "PPh 21 amount should be greater than 0")

        # Submit salary slip
        salary_slip.submit()

        # Verify GL entries
        gl_entries = frappe.get_all(
            "GL Entry",
            filters={"voucher_no": salary_slip.name},
            fields=["account", "debit", "credit"],
        )

        # Verify no BPJS payable entry
        bpjs_payable = next(
            (e for e in gl_entries if e.account == f"BPJS Payable - {self.company.abbr}"), None
        )
        self.assertIsNone(
            bpjs_payable, "BPJS Payable should not have a GL entry when BPJS is disabled"
        )

        # Verify other GL entries exist and balance
        total_debit = sum(flt(e.debit) for e in gl_entries)
        total_credit = sum(flt(e.credit) for e in gl_entries)
        self.assertEqual(flt(total_debit, 2), flt(total_credit, 2))


def run_payroll_integration_tests():
    """Run payroll integration tests"""
    import frappe.test_runner

    test_result = frappe.test_runner.run_tests(
        {
            "tests": [
                {
                    "module_name": "payroll_indonesia.payroll_indonesia.tests.test_payroll_integration",
                    "test_name": "TestPayrollIntegration",
                }
            ]
        }
    )
    return test_result
