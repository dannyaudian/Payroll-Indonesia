# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-06-29 02:35:42 by dannyaudian

"""
Salary Slip override for Indonesian payroll.
"""

from typing import Any, Dict

import frappe
from frappe import _
from frappe.utils import flt, getdate
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

# Import calculators
import payroll_indonesia.override.salary_slip.bpjs_calculator as bpjs_calc
import payroll_indonesia.override.salary_slip.tax_calculator as tax_calc
import payroll_indonesia.override.salary_slip.ter_calculator as ter_calc

# Import validation module
import payroll_indonesia.payroll_indonesia.validations as validations

# Import utilities
from payroll_indonesia.config.config import get_live_config
from payroll_indonesia.override.salary_slip.salary_utils import calculate_ytd_and_ytm
from payroll_indonesia.frappe_helpers import logger


class IndonesiaPayrollSalarySlip(SalarySlip):
    """
    Enhanced Salary Slip for Indonesian Payroll.
    Supports BPJS and PPh 21 tax calculations.
    """

    def validate(self) -> None:
        """
        Validate salary slip with Indonesian payroll requirements.
        """
        try:
            # Call parent validation first
            super().validate()

            # Validate employee data
            self._validate_employee_data()

            # Initialize additional fields
            self._initialize_fields()

            # Calculate components
            self.calculate()

            logger.info(f"Validation completed for {self.name}")
        except Exception as e:
            logger.exception(f"Error validating salary slip {self.name}: {e}")
            frappe.throw(_("Error validating salary slip: {0}").format(str(e)))

    def _validate_employee_data(self) -> None:
        """
        Validate employee data required for Indonesian payroll.
        """
        if not self.employee:
            frappe.throw(_("Employee is required"), title=_("Missing Data"))

        # Get employee document
        employee_doc = frappe.get_doc("Employee", self.employee)

        # Validate tax status if available
        if hasattr(employee_doc, "status_pajak"):
            validations.validate_tax_status(employee_doc.status_pajak)

        # Validate other employee fields
        validations.validate_employee_fields(employee_doc)

        # Store reference to employee document
        self.employee_doc = employee_doc

    def _initialize_fields(self) -> None:
        """
        Initialize additional fields required for Indonesian payroll.
        """
        default_fields = {
            "biaya_jabatan": 0,
            "netto": 0,
            "total_bpjs": 0,
            "kesehatan_employee": 0,
            "jht_employee": 0,
            "jp_employee": 0,
            "is_using_ter": 0,
            "ter_rate": 0,
            "ter_category": "",
            "koreksi_pph21": 0,
            "ytd_gross_pay": 0,
            "ytd_bpjs_deductions": 0,
            "pph21": 0,
        }

        # Set default values for missing fields
        for field, default in default_fields.items():
            if not hasattr(self, field) or getattr(self, field) is None:
                setattr(self, field, default)

    def calculate(self) -> None:
        """
        Calculate all components for Indonesian payroll.
        """
        # Get configuration
        cfg = get_live_config()

        # Calculate BPJS components
        self._calculate_bpjs()

        # Calculate YTD values
        self._calculate_ytd_values()

        # Calculate tax based on method from config
        self._calculate_tax(cfg)

        # Update totals
        self._update_totals()

    def _calculate_bpjs(self) -> None:
        """
        Calculate BPJS components using the BPJS calculator.
        """
        try:
            # Calculate BPJS components
            bpjs_components = bpjs_calc.calculate_components(self)

            # Store total BPJS employee contribution
            if hasattr(self, "total_bpjs"):
                self.total_bpjs = bpjs_components.get("total_employee", 0)

            # Store individual components
            for component in ["kesehatan_employee", "jht_employee", "jp_employee"]:
                if hasattr(self, component):
                    setattr(self, component, bpjs_components.get(component, 0))

            # Update BPJS components in deductions
            self._update_bpjs_deductions(bpjs_components)

            logger.debug(f"BPJS calculated for {self.name}: {bpjs_components}")
        except Exception as e:
            logger.exception(f"Error calculating BPJS: {e}")
            frappe.throw(_("Error calculating BPJS: {0}").format(str(e)))

    def _update_bpjs_deductions(self, components: Dict[str, float]) -> None:
        """
        Update BPJS component amounts in deductions.

        Args:
            components: Dictionary of calculated BPJS components
        """
        if not hasattr(self, "deductions") or not self.deductions:
            return

        # Mapping of component names to values
        component_map = {
            "BPJS Kesehatan Employee": "kesehatan_employee",
            "BPJS JHT Employee": "jht_employee",
            "BPJS JP Employee": "jp_employee",
        }

        # Update each component in deductions
        for deduction in self.deductions:
            component_name = getattr(deduction, "salary_component", "")
            if component_name in component_map:
                key = component_map[component_name]
                deduction.amount = components.get(key, 0)

    def _calculate_ytd_values(self) -> None:
        """
        Calculate YTD values for gross pay and BPJS deductions.
        """
        try:
            ytd_values = calculate_ytd_and_ytm(self)

            if hasattr(self, "ytd_gross_pay"):
                self.ytd_gross_pay = ytd_values.get("ytd", {}).get("ytd_gross", 0)

            if hasattr(self, "ytd_bpjs_deductions"):
                self.ytd_bpjs_deductions = ytd_values.get("ytd", {}).get("ytd_bpjs", 0)

            if hasattr(self, "ytd_pph21"):
                self.ytd_pph21 = ytd_values.get("ytd", {}).get("ytd_pph21", 0)

            logger.debug(f"YTD values calculated for {self.name}")
        except Exception as e:
            logger.warning(f"Error calculating YTD values: {e}")
            # Non-critical error, continue processing

    def _calculate_tax(self, cfg: Dict[str, Any]) -> None:
        """
        Calculate tax based on method from config.

        Args:
            cfg: Configuration dictionary
        """
        try:
            # Determine calculation method
            is_december = self._is_december_month()
            is_using_ter = self._should_use_ter(cfg)

            # Use appropriate calculation method
            if is_december:
                logger.info(f"Using December tax calculation for {self.name}")
                tax_calc.calculate_december_pph(self)
            elif is_using_ter:
                logger.info(f"Using TER tax calculation for {self.name}")
                ter_calc.calculate_monthly_pph_with_ter(self)
            else:
                logger.info(f"Using progressive tax calculation for {self.name}")
                tax_calc.calculate_monthly_pph_progressive(self)

            # Update PPh 21 component in deductions
            self._update_pph21_deduction()
        except Exception as e:
            logger.exception(f"Error calculating tax: {e}")
            frappe.throw(_("Error calculating tax: {0}").format(str(e)))

    def _is_december_month(self) -> bool:
        """
        Check if this is a December salary slip or has the December override flag.

        Returns:
            bool: True if December or override flag is set
        """
        # Check explicit override flag
        if hasattr(self, "is_december_override") and self.is_december_override:
            return True

        # Check if month is December
        if hasattr(self, "end_date") and self.end_date:
            end_date = getdate(self.end_date)
            return end_date.month == 12

        return False

    def _should_use_ter(self, cfg: Dict[str, Any]) -> bool:
        """
        Determine if TER calculation should be used based on config.

        Args:
            cfg: Configuration dictionary

        Returns:
            bool: True if TER should be used
        """
        # Check explicit flag first
        if hasattr(self, "is_using_ter") and self.is_using_ter:
            return True

        # Check config setting
        use_ter = cfg.get("tax", {}).get("use_ter_by_default", 0)

        # Check employee category if needed
        if use_ter and hasattr(self, "employee_doc"):
            emp_category = getattr(self.employee_doc, "employee_category", "")
            excluded_categories = cfg.get("tax", {}).get("ter_excluded_categories", [])

            if emp_category in excluded_categories:
                return False

        return bool(use_ter)

    def _update_pph21_deduction(self) -> None:
        """
        Update PPh 21 component in deductions with calculated amount.
        """
        if not hasattr(self, "deductions") or not self.deductions:
            return

        pph21_amount = flt(getattr(self, "pph21", 0))

        # Look for PPh 21 component in deductions
        for deduction in self.deductions:
            if getattr(deduction, "salary_component", "") == "PPh 21":
                deduction.amount = pph21_amount
                return

        # If not found and amount > 0, add it
        if pph21_amount > 0:
            # Add PPh 21 component if it doesn't exist
            self.append(
                "deductions",
                {
                    "salary_component": "PPh 21",
                    "amount": pph21_amount,
                    "default_amount": pph21_amount,
                    "abbr": "PPh21",
                },
            )

    def _update_totals(self) -> None:
        """
        Update total deduction to include BPJS and PPh 21.
        """
        if not hasattr(self, "total_deduction"):
            return

        # Calculate sum of all deductions to ensure consistency
        total = 0
        if hasattr(self, "deductions") and self.deductions:
            for deduction in self.deductions:
                total += flt(getattr(deduction, "amount", 0))

        self.total_deduction = total

        # Update net pay if gross pay exists
        if hasattr(self, "gross_pay") and hasattr(self, "net_pay"):
            self.net_pay = flt(self.gross_pay) - flt(self.total_deduction)

    def on_submit(self) -> None:
        """
        Process document on submission.
        Update related tax and BPJS records.
        """
        try:
            # Call parent submission handler
            super().on_submit()

            # Recalculate to ensure latest values
            self.calculate()

            # Update employee records with YTD values
            self._update_employee_ytd_records()

            logger.info(f"Salary slip {self.name} submitted successfully")
        except Exception as e:
            logger.exception(f"Error submitting salary slip {self.name}: {e}")
            frappe.throw(_("Error submitting salary slip: {0}").format(str(e)))

    def _update_employee_ytd_records(self) -> None:
        """
        Update employee's YTD records for tax and BPJS.
        """
        if not self.employee:
            return

        try:
            # Get current YTD values from employee
            ytd_pph21 = flt(frappe.db.get_value("Employee", self.employee, "ytd_pph21", 0))
            ytd_bpjs = flt(frappe.db.get_value("Employee", self.employee, "ytd_bpjs", 0))

            # Add current slip values
            new_ytd_pph21 = ytd_pph21 + flt(getattr(self, "pph21", 0))
            new_ytd_bpjs = ytd_bpjs + flt(getattr(self, "total_bpjs", 0))

            # Update employee record
            frappe.db.set_value(
                "Employee", 
                self.employee, 
                {"ytd_pph21": new_ytd_pph21, "ytd_bpjs": new_ytd_bpjs}
            )

            logger.debug(
                f"Updated YTD records for {self.employee}: "
                f"PPh21={new_ytd_pph21}, BPJS={new_ytd_bpjs}"
            )
        except Exception as e:
            logger.warning(f"Error updating employee YTD records: {e}")
            # Non-critical error, continue processing