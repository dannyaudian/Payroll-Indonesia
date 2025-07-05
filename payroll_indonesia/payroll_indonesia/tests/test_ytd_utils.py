# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import unittest
import frappe
from frappe.utils import flt, getdate, add_months, get_first_day, get_last_day
from payroll_indonesia.payroll_indonesia.utils import (
    get_ytd_total_taxable_income,
    get_ytd_pph_paid,
    clear_ytd_cache,
)


class TestYTDCalculations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up test environment and data"""
        cls.setup_test_employee()
        cls.setup_test_salary_slips()

    @classmethod
    def tearDownClass(cls):
        """Clean up test data"""
        frappe.db.rollback()
        clear_ytd_cache()

    @classmethod
    def setup_test_employee(cls):
        """Create test employee"""
        cls.test_employee = frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "YTD",
                "last_name": "Test Employee",
                "status": "Active",
                "company": frappe.defaults.get_user_default("Company"),
                "date_of_birth": add_months(getdate(), -(30 * 12)),
                "date_of_joining": add_months(getdate(), -12),
                "department": "All Departments",
                "gender": "Male",
                "status_pajak": "TK0",
                "npwp": "123456789012345",
            }
        ).insert(ignore_permissions=True)

    @classmethod
    def setup_test_salary_slips(cls):
        """Create test salary slips across multiple months"""
        cls.year = 2025
        cls.test_data = {
            # Month: [gross, bpjs_deductions, pph21, status]
            1: [15000000, 500000, 750000, "Submitted"],
            2: [15000000, 500000, 750000, "Submitted"],
            3: [16000000, 520000, 800000, "Submitted"],
            4: [16000000, 520000, 800000, "Cancelled"],  # Should be excluded
            5: [17000000, 540000, 850000, "Submitted"],
            6: [17000000, 540000, 850000, "Submitted"],
            7: [18000000, 560000, 900000, "Draft"],  # Should be excluded
            8: [18000000, 560000, 900000, "Submitted"],
            9: [19000000, 580000, 950000, "Submitted"],
        }

        cls.salary_slips = []
        for month, data in cls.test_data.items():
            gross, bpjs, pph21, status = data

            start_date = get_first_day(f"{cls.year}-{month:02d}-01")
            end_date = get_last_day(start_date)

            slip = frappe.get_doc(
                {
                    "doctype": "Salary Slip",
                    "employee": cls.test_employee.name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "posting_date": end_date,
                    "company": frappe.defaults.get_user_default("Company"),
                    "gross_pay": gross,
                    "total_bpjs": bpjs,
                    "monthly_tax": pph21,
                    "monthly_taxable_income": gross - bpjs,
                    "docstatus": (
                        1 if status == "Submitted" else (2 if status == "Cancelled" else 0)
                    ),
                }
            ).insert(ignore_permissions=True)

            cls.salary_slips.append(slip)

    def test_ytd_taxable_income_calculation(self):
        """Test YTD taxable income calculation"""
        # Test for September (month 9)
        ytd_taxable = get_ytd_total_taxable_income(self.test_employee.name, 9, self.year)

        # Calculate expected YTD taxable (only submitted slips)
        expected_ytd = sum(
            (data[0] - data[1])  # gross - bpjs
            for month, data in self.test_data.items()
            if month <= 9 and data[3] == "Submitted"
        )

        self.assertEqual(
            flt(ytd_taxable, 2), flt(expected_ytd, 2), "YTD taxable income calculation mismatch"
        )

    def test_ytd_pph_paid_calculation(self):
        """Test YTD PPh 21 paid calculation"""
        # Test for September (month 9)
        ytd_pph = get_ytd_pph_paid(self.test_employee.name, 9, self.year)

        # Calculate expected YTD PPh (only submitted slips)
        expected_pph = sum(
            data[2]  # pph21 amount
            for month, data in self.test_data.items()
            if month <= 9 and data[3] == "Submitted"
        )

        self.assertEqual(flt(ytd_pph, 2), flt(expected_pph, 2), "YTD PPh paid calculation mismatch")

    def test_progressive_accumulation(self):
        """Test progressive accumulation of YTD values"""
        # Test accumulation for each month
        for month in range(1, 10):
            ytd_taxable = get_ytd_total_taxable_income(self.test_employee.name, month, self.year)

            ytd_pph = get_ytd_pph_paid(self.test_employee.name, month, self.year)

            # Calculate expected values up to this month
            expected_taxable = sum(
                (data[0] - data[1])  # gross - bpjs
                for m, data in self.test_data.items()
                if m <= month and data[3] == "Submitted"
            )

            expected_pph = sum(
                data[2]  # pph21 amount
                for m, data in self.test_data.items()
                if m <= month and data[3] == "Submitted"
            )

            self.assertEqual(
                flt(ytd_taxable, 2),
                flt(expected_taxable, 2),
                f"YTD taxable progressive accumulation mismatch for month {month}",
            )

            self.assertEqual(
                flt(ytd_pph, 2),
                flt(expected_pph, 2),
                f"YTD PPh progressive accumulation mismatch for month {month}",
            )

    def test_cancelled_slip_exclusion(self):
        """Test that cancelled slips are excluded"""
        # April (month 4) has a cancelled slip
        ytd_april = get_ytd_total_taxable_income(self.test_employee.name, 4, self.year)

        # Calculate expected YTD excluding cancelled slip
        expected_april = sum(
            (data[0] - data[1])  # gross - bpjs
            for month, data in self.test_data.items()
            if month <= 4 and data[3] == "Submitted"
        )

        self.assertEqual(
            flt(ytd_april, 2),
            flt(expected_april, 2),
            "Cancelled slip not properly excluded from YTD calculation",
        )

    def test_draft_slip_exclusion(self):
        """Test that draft slips are excluded"""
        # July (month 7) has a draft slip
        ytd_july = get_ytd_total_taxable_income(self.test_employee.name, 7, self.year)

        # Calculate expected YTD excluding draft slip
        expected_july = sum(
            (data[0] - data[1])  # gross - bpjs
            for month, data in self.test_data.items()
            if month <= 7 and data[3] == "Submitted"
        )

        self.assertEqual(
            flt(ytd_july, 2),
            flt(expected_july, 2),
            "Draft slip not properly excluded from YTD calculation",
        )

    def test_cache_consistency(self):
        """Test cache consistency for repeated calls"""
        # First call - should compute and cache
        first_call = get_ytd_total_taxable_income(self.test_employee.name, 9, self.year)

        # Second call - should use cache
        second_call = get_ytd_total_taxable_income(self.test_employee.name, 9, self.year)

        self.assertEqual(flt(first_call, 2), flt(second_call, 2), "Cache inconsistency detected")

        # Clear cache and verify recomputation
        clear_ytd_cache()

        third_call = get_ytd_total_taxable_income(self.test_employee.name, 9, self.year)

        self.assertEqual(
            flt(first_call, 2), flt(third_call, 2), "Recomputed value mismatch after cache clear"
        )

    def test_invalid_month(self):
        """Test handling of invalid month"""
        with self.assertRaises(ValueError):
            get_ytd_total_taxable_income(self.test_employee.name, 13, self.year)  # Invalid month

    def test_future_month(self):
        """Test handling of future month"""
        # Test for December when data only exists until September
        ytd_december = get_ytd_total_taxable_income(self.test_employee.name, 12, self.year)

        # Should return same as September (last available month)
        ytd_september = get_ytd_total_taxable_income(self.test_employee.name, 9, self.year)

        self.assertEqual(
            flt(ytd_december, 2), flt(ytd_september, 2), "Future month handling incorrect"
        )


def run_ytd_utils_tests():
    """Run YTD utilities tests"""
    import frappe.test_runner

    test_result = frappe.test_runner.run_tests(
        {
            "tests": [
                {
                    "module_name": "payroll_indonesia.payroll_indonesia.tests.test_ytd_utils",
                    "test_name": "TestYTDCalculations",
                }
            ]
        }
    )
    return test_result
