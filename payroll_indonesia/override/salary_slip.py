# payroll_indonesia/override/salary_slip.py
"""
Custom Salary Slip override for Payroll Indonesia.

- TER (bulanan) & Progressive (Desember/annual correction).
- Flow Desember (sesuai arahan):
  * Jan–Nov diambil dari Annual Payroll History (APH).
  * Desember dihitung dari slip aktif (bruto, pengurang netto bulanan, biaya jabatan bulanan).
  * Tahunan = (Jan–Nov APH) + (Desember dari slip).
  * PPh Desember (koreksi) = PPh tahunan − total PPh Jan–Nov (APH).
- Selalu menulis baris "PPh 21" di deductions dan sinkron dengan UI.
"""

try:
    from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
except ImportError:
    from frappe.model.document import Document
    SalarySlip = Document
    import frappe
    frappe.log_error(
        message="Failed to import SalarySlip from hrms.payroll. Using Document fallback.",
        title="Payroll Indonesia Import Warning",
    )

import json
import traceback
import frappe
from frappe.utils import flt
try:
    from frappe.utils import getdate
except Exception:  # pragma: no cover
    from datetime import datetime
    def getdate(value):
        return datetime.strptime(str(value), "%Y-%m-%d")

from frappe.utils.safe_exec import safe_eval

# Hitung PPh
from payroll_indonesia.config.pph21_ter import calculate_pph21_TER
from payroll_indonesia.config.pph21_ter_december import (
    calculate_pph21_december,
    sum_bruto_earnings,               # ambil bruto taxable slip ini (Desember)
    sum_pengurang_netto_bulanan,      # pengurang netto bulanan (exclude Biaya Jabatan)
    biaya_jabatan_bulanan,            # min(5% × bruto_bulan, 500.000)
)

# Sinkronisasi Annual Payroll History
from payroll_indonesia.utils.sync_annual_payroll_history import sync_annual_payroll_history
from payroll_indonesia import _patch_salary_slip_globals

logger = frappe.logger("payroll_indonesia")


class CustomSalarySlip(SalarySlip):
    """Salary Slip override dengan logika PPh21 Indonesia."""

    # -------------------------
    # Helpers umum
    # -------------------------
    def _get_bulan_number(self, start_date=None, nama_bulan=None):
        bulan = None
        if start_date:
            try:
                bulan = getdate(start_date).month
            except Exception:
                logger.debug(f"Gagal parsing start_date: {start_date}")

        if not bulan and nama_bulan:
            peta = {
                "january": 1, "jan": 1, "januari": 1,
                "february": 2, "feb": 2, "februari": 2,
                "march": 3, "mar": 3, "maret": 3,
                "april": 4, "may": 5, "mei": 5,
                "june": 6, "jun": 6, "juni": 6,
                "july": 7, "jul": 7, "juli": 7,
                "august": 8, "aug": 8, "agustus": 8,
                "september": 9, "sep": 9,
                "october": 10, "oct": 10, "oktober": 10,
                "november": 11, "nov": 11,
                "december": 12, "dec": 12, "desember": 12,
            }
            bulan = peta.get(str(nama_bulan).strip().lower())

        if not bulan:
            from datetime import datetime
            bulan = datetime.now().month
        return bulan

    def get_employee_doc(self):
        if hasattr(self, "employee"):
            emp = self.employee
            if isinstance(emp, dict):
                return emp
            try:
                return frappe.get_doc("Employee", emp)
            except frappe.DoesNotExistError:
                frappe.log_error(
                    message=f"Employee '{emp}' not found for Salary Slip {self.name}",
                    title="Payroll Indonesia Missing Employee Error",
                )
                raise frappe.ValidationError(f"Employee '{emp}' not found.")
        return {}

    # -------------------------
    # Evaluasi formula
    # -------------------------
    def eval_condition_and_formula(self, struct_row, data):
        context = data.copy()
        context.update(_patch_salary_slip_globals())

        ssa = getattr(self, "salary_structure_assignment", None)
        for f in ("meal_allowance", "transport_allowance"):
            v = getattr(self, f, None)
            if v is None and ssa:
                v = ssa.get(f) if isinstance(ssa, dict) else getattr(ssa, f, None)
            if v is not None:
                context[f] = v

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
    # PPh 21 TER (bulanan)
    # -------------------------
    def calculate_income_tax(self):
        try:
            if not getattr(self, "employee", None):
                frappe.throw("Employee data is required for PPh21 calculation", title="Missing Employee")
            if not getattr(self, "company", None):
                frappe.throw("Company is required for PPh21 calculation", title="Missing Company")

            employee_doc = self.get_employee_doc()
            bulan = self._get_bulan_number(
                start_date=getattr(self, "start_date", None),
                nama_bulan=getattr(self, "bulan", None),
            )
            taxable_income = self._calculate_taxable_income()

            result = calculate_pph21_TER(
                taxable_income=taxable_income, employee=employee_doc, company=self.company, bulan=bulan
            )
            tax_amount = flt(result.get("pph21", 0.0))

            self.tax = tax_amount
            try:
                self.tax_type = "TER"
            except AttributeError:
                result["_tax_type"] = "TER"

            self.pph21_info = json.dumps(result)
            self.update_pph21_row(tax_amount)
            return tax_amount

        except frappe.ValidationError:
            raise
        except Exception as e:
            frappe.log_error(
                message=f"Failed to calculate income tax (TER): {e}\n{traceback.format_exc()}",
                title=f"Payroll Indonesia TER Calculation Error - {self.name}",
            )
            raise frappe.ValidationError(f"Error in PPh21 calculation: {e}")

    # -------------------------
    # Helper: ambil YTD Jan–Nov dari APH
    # -------------------------
    def _get_ytd_from_aph(self):
        """
        Kembalikan (ytd_bruto_jan_nov, ytd_netto_jan_nov, ytd_tax_paid_jan_nov)
        yang diambil dari Annual Payroll History (monthly_details bulan < 12).
        """
        ytd_bruto = 0.0
        ytd_netto = 0.0
        ytd_tax   = 0.0

        fiscal_year = getattr(self, "fiscal_year", None)
        if not fiscal_year and getattr(self, "start_date", None):
            fiscal_year = str(getdate(self.start_date).year)
        if not fiscal_year:
            return ytd_bruto, ytd_netto, ytd_tax

        try:
            rows = frappe.get_all(
                "Annual Payroll History",
                filters={"employee": self.employee, "fiscal_year": fiscal_year},
                fields=["name"],
                limit=1,
            )
            if rows:
                hist = frappe.get_doc("Annual Payroll History", rows[0].name)
                for r in hist.get("monthly_details", []) or []:
                    bln = getattr(r, "bulan", 0)
                    if bln and bln < 12:
                        ytd_bruto += flt(getattr(r, "bruto", 0))
                        # gunakan kolom netto jika tersedia; fallback: bruto - biaya_jabatan - pengurang_netto
                        r_netto = flt(getattr(r, "netto", 0))
                        if not r_netto:
                            r_netto = flt(getattr(r, "bruto", 0)) \
                                      - flt(getattr(r, "biaya_jabatan", 0)) \
                                      - flt(getattr(r, "pengurang_netto", 0))
                        ytd_netto += r_netto
                        ytd_tax   += flt(getattr(r, "pph21", 0))
        except Exception as e:
            logger.warning(f"Error fetching YTD from Annual Payroll History: {e}")

        return ytd_bruto, ytd_netto, ytd_tax

    # -------------------------
    # PPh 21 Progressive (Desember)
    # -------------------------
    def calculate_income_tax_december(self):
        """Hitung PPh21 Desember (annual correction) sesuai arahan Desember-only."""
        try:
            if not getattr(self, "employee", None):
                frappe.throw("Employee data is required for PPh21 calculation", title="Missing Employee")
            if not getattr(self, "company", None):
                frappe.throw("Company is required for PPh21 calculation", title="Missing Company")

            employee_doc = self.get_employee_doc()

            # === 1) Ambil YTD Jan–Nov dari APH ===
            ytd_bruto_jan_nov, ytd_netto_jan_nov, ytd_tax_paid_jan_nov = self._get_ytd_from_aph()

            # === 2) Ambil data Desember dari slip aktif ===
            slip_dict = self.as_dict()
            bruto_desember = sum_bruto_earnings(slip_dict)
            pengurang_netto_desember = sum_pengurang_netto_bulanan(slip_dict)
            biaya_jabatan_desember = biaya_jabatan_bulanan(bruto_desember)  # min(5% × bruto Des, 500k)

            # >>> PENTING: Baca JP+JHT (EE) bulan Desember dari deduction slip <<<
            jp_jht_employee_month = 0.0
            for d in (slip_dict.get("deductions") or []):
                name = (d.get("salary_component") or "").strip().lower()
                if name in {"bpjs jht employee", "bpjs jp employee"}:
                    jp_jht_employee_month += flt(d.get("amount", 0))

            # === 3) Hitung PPh21 Desember berbasis tahunan (December-only) ===
            result = calculate_pph21_december(
                employee=employee_doc,
                company=self.company,
                ytd_bruto_jan_nov=ytd_bruto_jan_nov,
                ytd_netto_jan_nov=ytd_netto_jan_nov,
                ytd_tax_paid_jan_nov=ytd_tax_paid_jan_nov,
                bruto_desember=bruto_desember,
                pengurang_netto_desember=pengurang_netto_desember,   # hanya untuk display
                biaya_jabatan_desember=biaya_jabatan_desember,
                # Dua opsi (pilih salah satu, yang bawah lebih eksplisit):
                # december_slip=slip_dict,
                jp_jht_employee_month=jp_jht_employee_month,
            )

            # Nilai pajak yang diposting untuk bulan Desember (koreksi)
            tax_amount = flt(result.get("pph21_bulan", 0.0))

            # Simpan ke field standar
            self.tax = tax_amount
            try:
                self.tax_type = "DECEMBER"
            except AttributeError:
                result["_tax_type"] = "DECEMBER"

            # Simpan detail ke pph21_info
            self.pph21_info = json.dumps(result)

            # Pastikan baris PPh21 di deductions ter-update
            self.update_pph21_row(tax_amount)

            # (Opsional) log audit
            frappe.logger().info(
                f"[DEC] {self.name} bruto_des={bruto_desember} bj_month={biaya_jabatan_desember} "
                f"jp_jht_month={jp_jht_employee_month} ytd_pph={ytd_tax_paid_jan_nov} -> tax_dec={tax_amount}"
            )
            return tax_amount

        except frappe.ValidationError:
            raise
        except Exception as e:
            frappe.log_error(
                message=f"Failed to calculate December income tax: {e}\n{traceback.format_exc()}",
                title=f"Payroll Indonesia December Calculation Error - {self.name}",
            )
            raise frappe.ValidationError(f"Error in December PPh21 calculation: {e}")
        
    # -------------------------
    # Utilitas lain
    # -------------------------
    def _calculate_taxable_income(self):
        return {
            "earnings": getattr(self, "earnings", []),
            "deductions": getattr(self, "deductions", []),
            "start_date": getattr(self, "start_date", None),
            "name": getattr(self, "name", None),
        }

    def update_pph21_row(self, tax_amount: float):
        try:
            target = "PPh 21"
            found = False
            for d in self.deductions:
                sc = d.get("salary_component") if isinstance(d, dict) else getattr(d, "salary_component", None)
                if sc == target:
                    if isinstance(d, dict):
                        d["amount"] = tax_amount
                    else:
                        d.amount = tax_amount
                    found = True
                    break
            if not found:
                self.append("deductions", {"salary_component": target, "amount": tax_amount})
            self._recalculate_totals()
        except Exception as e:
            frappe.log_error(
                message=f"Failed to update PPh21 row for {self.name}: {e}\n{traceback.format_exc()}",
                title="Payroll Indonesia PPh21 Row Update Error",
            )
            raise frappe.ValidationError(f"Error updating PPh21 component: {e}")

    def _recalculate_totals(self):
        try:
            if hasattr(self, "set_totals") and callable(getattr(self, "set_totals")):
                self.set_totals()
            elif hasattr(self, "calculate_totals") and callable(getattr(self, "calculate_totals")):
                self.calculate_totals()
            elif hasattr(self, "calculate_net_pay") and callable(getattr(self, "calculate_net_pay")):
                self.calculate_net_pay()
            else:
                self._manual_totals_calculation()
            self._update_rounded_values()
        except Exception:
            # fallback manual
            self._manual_totals_calculation()
            self._update_rounded_values()

    def _manual_totals_calculation(self):
        def row_amount(row):
            return row.get("amount", 0) if isinstance(row, dict) else getattr(row, "amount", 0)

        def flag(row, name):
            return (row.get(name, 0) if isinstance(row, dict) else getattr(row, name, 0)) or 0

        def include(row):
            return not (flag(row, "do_not_include_in_total") or flag(row, "statistical_component"))

        self.gross_pay = sum(row_amount(r) for r in (self.earnings or []) if include(r))
        self.total_deduction = sum(row_amount(r) for r in (self.deductions or []) if include(r))
        self.net_pay = (self.gross_pay or 0) - (self.total_deduction or 0)
        if hasattr(self, "total"):
            self.total = self.net_pay

    def _update_rounded_values(self):
        try:
            if hasattr(self, "rounded_total") and hasattr(self, "total"):
                self.rounded_total = round(getattr(self, "total", self.net_pay))
            if hasattr(self, "rounded_net_pay"):
                self.rounded_net_pay = round(self.net_pay)
            if hasattr(self, "net_pay_in_words"):
                try:
                    from frappe.utils import money_in_words
                    self.net_pay_in_words = money_in_words(self.net_pay, getattr(self, "currency", "IDR"))
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to update rounded values for {self.name}: {e}")

    # -------------------------
    # Hook validate & sync history
    # -------------------------
    def validate(self):
        try:
            try:
                super().validate()
            except frappe.ValidationError:
                raise
            except Exception as e:
                frappe.log_error(
                    message=f"Error in parent validate for Salary Slip {self.name}: {e}\n{traceback.format_exc()}",
                    title="Payroll Indonesia Validation Error",
                )

            if getattr(self, "tax_type", "") == "DECEMBER":
                tax_amount = self.calculate_income_tax_december()
            else:
                tax_amount = self.calculate_income_tax()

            self.update_pph21_row(tax_amount)
            logger.info(f"Validate: Updated PPh21 deduction row to {tax_amount}")

        except frappe.ValidationError:
            raise
        except Exception as e:
            frappe.log_error(
                message=f"Failed to update PPh21 in validate for Salary Slip {self.name}: {e}\n{traceback.format_exc()}",
                title="Payroll Indonesia PPh21 Update Error",
            )
            raise frappe.ValidationError(f"Error calculating PPh21: {e}")

    # -------------------------
    # Annual Payroll History sync
    # -------------------------
    def sync_to_annual_payroll_history(self, result, mode="monthly"):
        # Catatan: Bila Anda TIDAK ingin menulis APH sama sekali,
        # Anda bisa menonaktifkan pemanggilan fungsi ini di on_submit/on_cancel.
        if getattr(self, "_annual_history_synced", False):
            return

        try:
            if not getattr(self, "employee", None):
                logger.warning(f"No employee for Salary Slip {getattr(self, 'name', 'unknown')}, skip sync")
                return

            employee_doc = self.get_employee_doc() or {}
            employee_info = {
                "name": employee_doc.get("name") or self.employee,
                "company": employee_doc.get("company") or getattr(self, "company", None),
                "employee_name": employee_doc.get("employee_name"),
            }

            fiscal_year = getattr(self, "fiscal_year", None)
            if not fiscal_year and getattr(self, "start_date", None):
                fiscal_year = str(getdate(self.start_date).year)
            if not fiscal_year:
                logger.warning(f"Could not determine fiscal year for Salary Slip {self.name}, skipping sync")
                return

            nomor_bulan = self._get_bulan_number(
                start_date=getattr(self, "start_date", None),
                nama_bulan=getattr(self, "bulan", None),
            )

            raw_rate = result.get("rate", 0)
            numeric_rate = raw_rate if isinstance(raw_rate, (int, float)) else 0

            monthly_result = {
                "bulan": nomor_bulan,
                "bruto": result.get("bruto", result.get("bruto_total", 0)),
                "pengurang_netto": result.get("pengurang_netto", result.get("income_tax_deduction_total", 0)),
                "biaya_jabatan": result.get("biaya_jabatan", result.get("biaya_jabatan_total", 0)),
                "netto": result.get("netto", result.get("netto_total", 0)),
                "pkp": result.get("pkp", result.get("pkp_annual", 0)),
                "rate": flt(numeric_rate),
                "pph21": result.get("pph21", result.get("pph21_bulan", 0)),
                "salary_slip": self.name,
            }

            if mode == "monthly":
                sync_annual_payroll_history(
                    employee=employee_info, fiscal_year=fiscal_year, monthly_results=[monthly_result], summary=None
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
                if isinstance(raw_rate, str) and raw_rate:
                    summary["rate_slab"] = raw_rate
                sync_annual_payroll_history(
                    employee=employee_info, fiscal_year=fiscal_year, monthly_results=[monthly_result], summary=summary
                )

            self._annual_history_synced = True

        except frappe.ValidationError:
            raise
        except Exception as e:
            frappe.log_error(
                message=f"Failed to sync Annual Payroll History for {getattr(self, 'name', 'unknown')}: {e}\n{traceback.format_exc()}",
                title="Payroll Indonesia Annual History Sync Error",
            )
            logger.warning(f"Annual Payroll History sync failed for {self.name}: {e}")

    def on_submit(self):
        try:
            info = json.loads(getattr(self, "pph21_info", "{}") or "{}")
        except Exception:
            info = {}
        tax_type = getattr(self, "tax_type", None) or info.get("_tax_type")
        if not tax_type:
            bulan = self._get_bulan_number(start_date=getattr(self, "start_date", None))
            if bulan == 12:
                tax_type = "DECEMBER"
        mode = "december" if tax_type == "DECEMBER" else "monthly"
        self.sync_to_annual_payroll_history(info, mode=mode)
        if getattr(self, "_annual_history_synced", False):
            frappe.logger().info(f"[SYNC] Salary Slip {self.name} synced to Annual Payroll History")

    def on_cancel(self):
        if getattr(self, "flags", {}).get("from_annual_payroll_cancel"):
            return
        try:
            if not getattr(self, "employee", None):
                logger.warning(f"No employee for cancelled Salary Slip {getattr(self, 'name', 'unknown')}, skip")
                return

            fiscal_year = getattr(self, "fiscal_year", None) or str(getattr(self, "start_date", ""))[:4]
            if not fiscal_year:
                logger.warning(f"Could not determine fiscal year for cancelled Salary Slip {self.name}, skipping sync")
                return

            try:
                info = json.loads(getattr(self, "pph21_info", "{}") or "{}")
            except Exception:
                info = {}

            tax_type = getattr(self, "tax_type", None) or info.get("_tax_type")
            if not tax_type:
                bulan = self._get_bulan_number(start_date=getattr(self, "start_date", None))
                if bulan == 12:
                    tax_type = "DECEMBER"
            mode = "december" if tax_type == "DECEMBER" else "monthly"

            sync_annual_payroll_history(
                employee=self.employee,
                fiscal_year=fiscal_year,
                monthly_results=None,
                summary=None,
                cancelled_salary_slip=self.name,
                mode=mode,
            )
            frappe.logger().info(f"[SYNC] Salary Slip {self.name} removed from Annual Payroll History")
        except frappe.ValidationError:
            raise
        except Exception as e:
            frappe.log_error(
                message=f"Failed to remove from Annual Payroll History on cancel for {getattr(self, 'name', 'unknown')}: {e}\n{traceback.format_exc()}",
                title="Payroll Indonesia Annual History Cancel Error",
            )
            logger.warning(f"Failed to update Annual Payroll History when cancelling {self.name}: {e}")


def on_submit(doc, method=None):
    if isinstance(doc, CustomSalarySlip):
        return
    doc.__class__ = CustomSalarySlip
    doc.on_submit()


def on_cancel(doc, method=None):
    if isinstance(doc, CustomSalarySlip):
        return
    doc.__class__ = CustomSalarySlip
    doc.on_cancel()
