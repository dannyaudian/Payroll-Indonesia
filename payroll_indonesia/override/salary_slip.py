"""Custom Salary Slip override for Payroll Indonesia.

This module extends the standard ``Salary Slip`` doctype with Indonesian
income tax logic (PPh 21) and adds helper globals for salary component
formula evaluation.

Rewrite: Ensure PPh 21 row in deductions updates and syncs with UI using attribute-safe operations.
Fix: Do not assign dict directly to DocType field (pph21_info), use JSON string.
"""

try:
    from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
except Exception:
    SalarySlip = object

import frappe
import json
from frappe.utils import flt
from frappe.utils.safe_exec import safe_eval

from payroll_indonesia.config import pph21_ter, pph21_ter_december
from payroll_indonesia.utils import sync_annual_payroll_history
from payroll_indonesia import _patch_salary_slip_globals


class CustomSalarySlip(SalarySlip):
    """
    Salary Slip with Indonesian income tax calculations (TER bulanan dan Progressive/Desember).
    Koreksi PPh21 minus: PPh21 di slip minus, THP otomatis bertambah oleh sistem.
    Sinkronisasi ke Annual Payroll History setiap kali slip dihitung atau dibatalkan.
    """

    # -------------------------
    # Formula evaluation
    # -------------------------
    def eval_condition_and_formula(self, struct_row, data):
        """Evaluate condition and formula with additional Payroll Indonesia globals."""
        context = data.copy()
        context.update(_patch_salary_slip_globals())

        try:
            if getattr(struct_row, "condition", None):
                if not safe_eval(struct_row.condition, context):
                    return 0

            if getattr(struct_row, "formula", None):
                return safe_eval(struct_row.formula, context)

        except Exception as e:
            frappe.throw(
                f"Failed evaluating formula for {getattr(struct_row, 'salary_component', 'component')}: {e}"
            )

        return super().eval_condition_and_formula(struct_row, data)

    # -------------------------
    # Income tax calculation (PPh 21)
    # -------------------------
    def calculate_income_tax(self):
        """
        Override perhitungan PPh 21 (TER/Progresif).
        Setelah dihitung, update komponen PPh 21 di deductions agar muncul di UI.
        """
        employee_doc = self.get_employee_doc()

        slip_data = {
            "earnings": getattr(self, "earnings", []),
            "deductions": getattr(self, "deductions", []),
        }

        result = pph21_ter.calculate_pph21_TER(employee_doc, slip_data)
        tax_amount = flt(result.get("pph21", 0.0))

        # Store details as JSON string (pph21_info field is Text)
        self.pph21_info = json.dumps(result)

        # Set standard Salary Slip fields
        self.tax = tax_amount
        self.tax_type = "TER"

        self.update_pph21_row(tax_amount)
        self.sync_to_annual_payroll_history(result, mode="monthly")
        return tax_amount

    def calculate_income_tax_december(self):
        """Calculate annual progressive PPh21 for December."""
        employee_doc = self.get_employee_doc()

        slip_data = {
            "earnings": getattr(self, "earnings", []),
            "deductions": getattr(self, "deductions", []),
        }

        result = pph21_ter_december.calculate_pph21_TER_december(
            employee_doc, [slip_data]
        )
        tax_amount = flt(result.get("pph21_month", 0.0))

        self.pph21_info = json.dumps(result)

        self.tax = tax_amount
        self.tax_type = "DECEMBER"

        self.update_pph21_row(tax_amount)
        self.sync_to_annual_payroll_history(result, mode="december")
        return tax_amount

    def update_pph21_row(self, tax_amount: float):
        """Ensure the ``PPh 21`` deduction row exists and update its amount (sync with UI)."""
        target_component = "PPh 21"
        found = False

        # Handle both child table object and dict cases for ERPNext/Frappe
        for d in self.deductions:
            sc = getattr(d, "salary_component", None) if hasattr(d, "salary_component") else d.get("salary_component")
            if sc == target_component:
                if hasattr(d, "amount"):
                    d.amount = tax_amount
                else:
                    d["amount"] = tax_amount
                found = True
                break

        if not found:
            self.append(
                "deductions",
                {
                    "salary_component": target_component,
                    "amount": tax_amount,
                },
            )

        # Refresh total deduction dan net pay, attribute/dict safe
        self.total_deduction = sum([
            getattr(row, "amount", row.get("amount", 0)) if hasattr(row, "amount") else row.get("amount", 0)
            for row in self.deductions
        ])
        self.net_pay = (self.gross_pay or 0) - self.total_deduction

    def validate(self):
        """Ensure PPh 21 deduction row updated before saving."""
        try:
            super().validate()
        except Exception:
            pass

        if getattr(self, "tax_type", "") == "DECEMBER":
            tax_amount = self.calculate_income_tax_december()
        else:
            tax_amount = self.calculate_income_tax()
        self.update_pph21_row(tax_amount)
        frappe.logger().info(f"Validate: Updated PPh21 deduction row to {tax_amount}")

    # -------------------------
    # Helpers
    # -------------------------
    def get_employee_doc(self):
        """Helper: get employee doc/dict from self.employee (id, dict, or object)."""
        if hasattr(self, "employee"):
            emp = self.employee
            if isinstance(emp, dict):
                return emp
            try:
                return frappe.get_doc("Employee", emp)
            except Exception:
                return {}
        return {}

    # -------------------------
    # Annual Payroll History sync
    # -------------------------
    def sync_to_annual_payroll_history(self, result, mode="monthly"):
        """Sync slip result to Annual Payroll History."""
        try:
            employee_doc = self.get_employee_doc()
            fiscal_year = getattr(self, "fiscal_year", None) or str(
                getattr(self, "start_date", None) or ""
            )[:4]
            if not fiscal_year:
                return

            monthly_result = {
                "bulan": getattr(self, "month", None) or getattr(self, "bulan", None),
                "bruto": result.get("bruto", result.get("bruto_total", 0)),
                "pengurang_netto": result.get(
                    "pengurang_netto", result.get("income_tax_deduction_total", 0)
                ),
                "biaya_jabatan": result.get("biaya_jabatan", result.get("biaya_jabatan_total", 0)),
                "netto": result.get("netto", result.get("netto_total", 0)),
                "pkp": result.get("pkp", result.get("pkp_annual", 0)),
                "rate": result.get("rate", ""),
                "pph21": result.get("pph21", result.get("pph21_month", 0)),
                "salary_slip": self.name,
            }

            if mode == "monthly":
                sync_annual_payroll_history.sync_annual_payroll_history(
                    employee=employee_doc,
                    fiscal_year=fiscal_year,
                    monthly_results=[monthly_result],
                    summary=None,
                )
            elif mode == "december":
                summary = {
                    "bruto_total": result.get("bruto_total", 0),
                    "netto_total": result.get("netto_total", 0),
                    "ptkp_annual": result.get("ptkp_annual", 0),
                    "pkp_annual": result.get("pkp_annual", 0),
                    "pph21_annual": result.get("pph21_annual", 0),
                    "koreksi_pph21": result.get("koreksi_pph21", 0),
                }
                sync_annual_payroll_history.sync_annual_payroll_history(
                    employee=employee_doc,
                    fiscal_year=fiscal_year,
                    monthly_results=[monthly_result],
                    summary=summary,
                )
        except Exception as e:
            frappe.logger().error(f"Failed to sync Annual Payroll History: {e}")

    def on_cancel(self):
        """When slip is cancelled, remove related row from Annual Payroll History."""
        try:
            employee_doc = self.get_employee_doc()
            fiscal_year = (
                getattr(self, "fiscal_year", None) or str(getattr(self, "start_date", ""))[:4]
            )
            if not fiscal_year:
                return
            sync_annual_payroll_history.sync_annual_payroll_history(
                employee=employee_doc,
                fiscal_year=fiscal_year,
                monthly_results=None,
                summary=None,
                cancelled_salary_slip=self.name,
            )
        except Exception as e:
            frappe.logger().error(f"Failed to remove from Annual Payroll History on cancel: {e}")
            