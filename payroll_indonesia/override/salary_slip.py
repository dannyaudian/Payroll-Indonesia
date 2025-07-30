"""Custom Salary Slip override for Payroll Indonesia.

Adds Indonesian income tax logic and patches ``eval_condition_and_formula`` so
that helper functions defined in ``hooks.salary_slip_globals`` are available when
evaluating Salary Component formulas.

Rewrite: After computing self.tax, ensure a row exists in self.deductions with
salary_component = "PPh 21" and amount = self.tax. Update the row if already present.
"""

try:
    from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
except Exception:
    SalarySlip = object

import frappe
from frappe.utils.safe_exec import safe_eval
import json

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
        gross_income = self.gross_pay or sum([row.amount for row in self.earnings])

        # Hitung PTKP
        ptkp = pph21_ter.get_ptkp_amount(employee_doc)
        netto = gross_income  # sementara tanpa biaya jabatan
        pkp = max(netto - ptkp, 0)

        # Ambil kode TER dari Employee
        ter_code = pph21_ter.get_ter_code(employee_doc)

        # Hitung rate berdasarkan TER
        rate = 0.0
        if ter_code:
            rate = pph21_ter.get_ter_rate(ter_code, gross_income)

        tax_amount = flt((pkp * rate) / 100)

        # Simpan detail di info
        self.pph21_info = {
            "ptkp": ptkp,
            "bruto": gross_income,
            "netto": netto,
            "pkp": pkp,
            "rate": rate,
            "pph21": tax_amount,
        }

        # Update komponen PPh 21 di deductions
        self.set_income_tax_component(tax_amount)

        return tax_amount

    def set_income_tax_component(self, tax_amount: float):
        """
        Pastikan komponen "PPh 21" selalu ada di deductions,
        update amount sesuai hasil kalkulasi Python.
        """
        target_component = "PPh 21"
        found = False

        for d in self.deductions:
            if d.salary_component == target_component:
                d.amount = tax_amount
                found = True
                break

        if not found:
            self.append("deductions", {
                "salary_component": target_component,
                "amount": tax_amount,
            })

        # Refresh total deduction dan net pay
        self.total_deduction = sum([row.amount for row in self.deductions])
        self.net_pay = (self.gross_pay or 0) - self.total_deduction

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
            fiscal_year = getattr(self, "fiscal_year", None) or str(getattr(self, "start_date", ""))[:4]
            if not fiscal_year:
                return

            monthly_result = {
                "bulan": getattr(self, "month", None) or getattr(self, "bulan", None),
                "bruto": result.get("bruto", result.get("bruto_total", 0)),
                "pengurang_netto": result.get("pengurang_netto", result.get("income_tax_deduction_total", 0)),
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
            fiscal_year = getattr(self, "fiscal_year", None) or str(getattr(self, "start_date", ""))[:4]
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