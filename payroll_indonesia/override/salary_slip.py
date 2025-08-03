"""Custom Salary Slip override for Payroll Indonesia.

This module extends the standard ``Salary Slip`` doctype with Indonesian
income tax logic (PPh 21) and adds helper globals for salary component
formula evaluation.

Rewrite: Ensure PPh 21 row in deductions updates and syncs with UI using attribute-safe operations.
Fix: Do not assign dict directly to DocType field (pph21_info), use JSON string.
Update: Replace manual total calculations with ERPNext/Frappe's built-in methods.
Update: Improve exception handling to catch specific expected exceptions and re-raise unexpected ones.
Update: Fix circular import issues by using direct imports for tax calculation functions.
"""

try:
    from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
except ImportError:
    from frappe.model.document import Document
    SalarySlip = Document  # safer fallback for tests/static analysis
    import frappe
    frappe.log_error(
        message="Failed to import SalarySlip from hrms.payroll. Using Document fallback.",
        title="Payroll Indonesia Import Warning"
    )

import frappe
import json
import traceback
from frappe.utils import flt
try:
    from frappe.utils import getdate
except Exception:  # pragma: no cover - fallback for test stubs without getdate
    from datetime import datetime

    def getdate(value):
        return datetime.strptime(str(value), "%Y-%m-%d")
from frappe.utils.safe_exec import safe_eval

# Import tax calculation functions directly (better pattern to avoid circular imports)
from payroll_indonesia.config.pph21_ter import calculate_pph21_TER
from payroll_indonesia.config.pph21_ter_december import calculate_pph21_december
# Import sync function directly
from payroll_indonesia.utils.sync_annual_payroll_history import sync_annual_payroll_history
from payroll_indonesia import _patch_salary_slip_globals

# Setup global logger for consistent logging
logger = frappe.logger("payroll_indonesia")

class CustomSalarySlip(SalarySlip):
    """
    Salary Slip with Indonesian income tax calculations (TER bulanan dan Progressive/Desember).
    Koreksi PPh21 minus: PPh21 di slip minus, THP otomatis bertambah oleh sistem.
    Sinkronisasi ke Annual Payroll History setiap kali slip dihitung atau dibatalkan.
    """

    # -------------------------
    # Helper methods
    # -------------------------
    def _get_bulan_number(self, start_date=None, nama_bulan=None):
        """
        Ambil nomor bulan dari tanggal atau nama bulan.

        Args:
            start_date: String tanggal YYYY-MM-DD atau None
            nama_bulan: Nama bulan (misal 'January', 'Jan', 'Januari') atau None

        Returns:
            int: Nomor bulan (1-12) atau bulan saat ini jika keduanya tidak valid
        """
        bulan = None

        # Coba dapatkan bulan dari start_date terlebih dahulu
        if start_date:
            try:
                bulan = getdate(start_date).month
            except Exception:
                # Log kesalahan untuk debug tetapi lanjutkan ke fallback
                logger.debug(f"Gagal mengambil bulan dari tanggal: {start_date}")
                pass

        # Jika masih None, coba dari nama_bulan
        if not bulan and nama_bulan:
            peta_bulan = {
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
            bulan = peta_bulan.get(str(nama_bulan).strip().lower())

        # Jika masih belum ada, gunakan bulan berjalan
        if not bulan:
            from datetime import datetime
            bulan = datetime.now().month
            logger.debug(f"Menggunakan bulan saat ini ({bulan}) sebagai fallback")

        return bulan

    def get_employee_doc(self):
        """Helper: get employee doc/dict from self.employee (id, dict, or object)."""
        if hasattr(self, "employee"):
            emp = self.employee
            if isinstance(emp, dict):
                return emp
            try:
                return frappe.get_doc("Employee", emp)
            except frappe.DoesNotExistError:
                # Specific handling for missing employee record
                frappe.log_error(
                    message=f"Employee '{emp}' not found for Salary Slip {self.name}",
                    title="Payroll Indonesia Missing Employee Error"
                )
                raise frappe.ValidationError(f"Employee '{emp}' not found. Please check employee record.")
            except Exception as e:
                frappe.log_error(
                    message=f"Failed to get Employee document for {emp}: {str(e)}",
                    title="Payroll Indonesia Employee Error"
                )
                raise frappe.ValidationError(f"Error fetching employee data: {str(e)}")
        return {}

    # -------------------------
    # Formula evaluation
    # -------------------------
    def eval_condition_and_formula(self, struct_row, data):
        """Evaluate condition and formula with additional Payroll Indonesia globals."""
        context = data.copy()
        context.update(_patch_salary_slip_globals())

        # Inject custom allowance fields so formulas can reference them
        ssa = getattr(self, "salary_structure_assignment", None)
        for field in ("meal_allowance", "transport_allowance"):
            value = getattr(self, field, None)
            if value is None and ssa:
                if isinstance(ssa, dict):
                    value = ssa.get(field)
                else:
                    value = getattr(ssa, field, None)
            if value is not None:
                context[field] = value

        try:
            if getattr(struct_row, "condition", None):
                if not safe_eval(struct_row.condition, context):
                    return 0

            if getattr(struct_row, "formula", None):
                return safe_eval(struct_row.formula, context)

        except Exception as e:
            # Formula evaluation failures are critical and should always stop processing
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
        try:
            # Basic validation
            if not hasattr(self, "employee") or not self.employee:
                frappe.throw("Employee data is required for PPh21 calculation", title="Missing Employee")
                
            if not hasattr(self, "company") or not self.company:
                frappe.throw("Company is required for PPh21 calculation", title="Missing Company")
            
            employee_doc = self.get_employee_doc()
            
            # Ambil nomor bulan menggunakan helper
            bulan = self._get_bulan_number(
                start_date=getattr(self, "start_date", None),
                nama_bulan=getattr(self, "bulan", None)
            )
            
            # Calculate taxable income
            taxable_income = self._calculate_taxable_income()

            # Calculate PPh21 using standardized interface
            result = calculate_pph21_TER(
                taxable_income=taxable_income,
                employee=employee_doc,
                company=self.company,
                bulan=bulan
            )
            
            tax_amount = flt(result.get("pph21", 0.0))

            # Store details as JSON string (pph21_info field is Text)
            self.pph21_info = json.dumps(result)

            # Set standard Salary Slip fields
            self.tax = tax_amount
            self.tax_type = "TER"

            self.update_pph21_row(tax_amount)
            return tax_amount
            
        except frappe.ValidationError as ve:
            # Expected validation errors - re-raise to stop processing
            logger.warning(f"Validation error in TER calculation for {self.name}: {str(ve)}")
            raise
            
        except Exception as e:
            error_trace = traceback.format_exc()
            error_msg = f"Failed to calculate income tax (TER): {str(e)}"
            frappe.log_error(
                message=f"{error_msg}\n{error_trace}",
                title=f"Payroll Indonesia TER Calculation Error - {self.name}"
            )
            # Unexpected errors are converted to ValidationError to stop processing
            raise frappe.ValidationError(f"Error in PPh21 calculation: {str(e)}")

    def calculate_income_tax_december(self):
        """Calculate annual progressive PPh21 for December."""
        try:
            # Basic validation
            if not hasattr(self, "employee") or not self.employee:
                frappe.throw("Employee data is required for PPh21 calculation", title="Missing Employee")
                
            if not hasattr(self, "company") or not self.company:
                frappe.throw("Company is required for PPh21 calculation", title="Missing Company")
            
            employee_doc = self.get_employee_doc()
            
            # Ambil pendapatan kena pajak untuk bulan ini
            taxable_income = self._calculate_taxable_income()
            
            # Fetch YTD income and YTD tax paid
            ytd_income, ytd_tax_paid = self._get_ytd_income_and_tax()
            
            # Calculate December tax using standardized interface
            result = calculate_pph21_december(
                taxable_income=taxable_income,
                employee=employee_doc,
                company=self.company,
                ytd_income=ytd_income,
                ytd_tax_paid=ytd_tax_paid
            )
            
            tax_amount = flt(result.get("pph21_bulan", 0.0))

            # Store details as JSON string
            self.pph21_info = json.dumps(result)

            # Set standard fields
            self.tax = tax_amount
            self.tax_type = "DECEMBER"

            self.update_pph21_row(tax_amount)
            return tax_amount
            
        except frappe.ValidationError as ve:
            # Expected validation errors - re-raise to stop processing
            logger.warning(f"Validation error in December calculation for {self.name}: {str(ve)}")
            raise
            
        except Exception as e:
            error_trace = traceback.format_exc()
            error_msg = f"Failed to calculate December income tax: {str(e)}"
            frappe.log_error(
                message=f"{error_msg}\n{error_trace}",
                title=f"Payroll Indonesia December Calculation Error - {self.name}"
            )
            # Unexpected errors are converted to ValidationError to stop processing
            raise frappe.ValidationError(f"Error in December PPh21 calculation: {str(e)}")
    
    def _calculate_taxable_income(self):
        """
        Calculate taxable income from earnings and deductions.
        Returns a dictionary with earnings and deductions that can be passed to tax calculation functions.
        """
        return {
            "earnings": getattr(self, "earnings", []),
            "deductions": getattr(self, "deductions", []),
            "start_date": getattr(self, "start_date", None),
            "name": getattr(self, "name", None),
        }
    
    def _get_ytd_income_and_tax(self):
        """
        Hitung pendapatan dan pajak tahun berjalan (tidak termasuk bulan ini).
        Digunakan untuk perhitungan pajak Desember.

        Returns:
            tuple: (ytd_income, ytd_tax_paid)
        """
        ytd_income = 0.0
        ytd_tax_paid = 0.0
        
        # Try to determine fiscal year
        fiscal_year = getattr(self, "fiscal_year", None)
        if not fiscal_year and hasattr(self, "start_date") and self.start_date:
            fiscal_year = str(getdate(self.start_date).year)
        
        if not fiscal_year:
            # Can't determine year, use default values
            return ytd_income, ytd_tax_paid
        
        try:
            # Try to fetch Annual Payroll History
            filters = {
                "employee": self.employee,
                "fiscal_year": fiscal_year,
            }
            
            annual_history = frappe.get_all(
                "Annual Payroll History",
                filters=filters,
                fields=["name"],
            )
            
            if annual_history:
                # Get the first record (should be only one per employee per year)
                history_doc = frappe.get_doc("Annual Payroll History", annual_history[0].name)
                
                # Jumlahkan seluruh entri bulanan kecuali Desember
                for row in history_doc.get("monthly_details", []):
                    bulan = getattr(row, "bulan", 0)
                    if bulan < 12:  # Exclude December
                        ytd_income += flt(getattr(row, "bruto", 0))
                        ytd_tax_paid += flt(getattr(row, "pph21", 0))
        
        except Exception as e:
            logger.warning(f"Error fetching YTD income and tax: {str(e)}")
            # Continue with default values if there's an error
        
        return ytd_income, ytd_tax_paid

    def update_pph21_row(self, tax_amount: float):
        """
        Ensure the ``PPh 21`` deduction row exists and update its amount (sync with UI).
        Uses ERPNext/Frappe's built-in methods to recalculate totals.
        """
        try:
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

            # Use built-in methods to recalculate totals
            self._recalculate_totals()
            
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Failed to update PPh21 row for {self.name}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia PPh21 Row Update Error"
            )
            # This function is critical for correct salary slip values, so we must raise
            raise frappe.ValidationError(f"Error updating PPh21 component: {str(e)}")

    def _recalculate_totals(self):
        """
        Recalculate all totals using built-in methods where available.
        Falls back to manual calculation if built-in methods are not available.
        """
        try:
            # Try to use built-in ERPNext/Frappe methods for recalculation
            if hasattr(self, "set_totals") and callable(getattr(self, "set_totals")):
                self.set_totals()
            elif hasattr(self, "calculate_totals") and callable(getattr(self, "calculate_totals")):
                self.calculate_totals()
            else:
                # Fallback to calculate_net_pay if available
                if hasattr(self, "calculate_net_pay") and callable(getattr(self, "calculate_net_pay")):
                    self.calculate_net_pay()
                else:
                    # Last resort: manual calculation (legacy fallback)
                    self._manual_totals_calculation()
                    
            # Ensure rounded values are also updated
            self._update_rounded_values()
            
        except frappe.ValidationError as ve:
            # Pass through validation errors (expected)
            raise
            
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Failed to recalculate totals for {getattr(self, 'name', 'unknown')}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia Totals Calculation Error"
            )
            # Fallback to manual calculation
            try:
                self._manual_totals_calculation()
            except Exception as manual_error:
                # If even manual calculation fails, we need to stop processing
                raise frappe.ValidationError(f"Cannot calculate salary slip totals: {str(manual_error)}")

    def _manual_totals_calculation(self):
        """
        Manual calculation of totals as a fallback when built-in methods fail.
        """
        try:
            # Calculate total deduction
            self.total_deduction = sum(
                getattr(row, "amount", 0) if hasattr(row, "amount") else row.get("amount", 0)
                for row in self.deductions
            )
            
            # Calculate net pay
            self.net_pay = (self.gross_pay or 0) - self.total_deduction
            
            # Update other fields that might depend on these calculations
            if hasattr(self, "rounded_total"):
                self.rounded_total = round(self.total_deduction)
            
            if hasattr(self, "net_pay_in_words"):
                # Try to use money_in_words if available
                try:
                    from frappe.utils import money_in_words
                    self.net_pay_in_words = money_in_words(self.net_pay, getattr(self, "currency", "IDR"))
                except ImportError:
                    # Skip if money_in_words is not available
                    pass
                    
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Manual totals calculation failed for {self.name}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia Manual Calculation Error"
            )
            # This is a critical error as it means we can't calculate the slip correctly
            raise frappe.ValidationError(f"Failed to calculate salary slip totals: {str(e)}")

    def _update_rounded_values(self):
        """
        Update rounded values to ensure they're synchronized with calculated values.
        """
        try:
            # Update rounded_total if it exists
            if hasattr(self, "rounded_total") and hasattr(self, "total"):
                self.rounded_total = round(getattr(self, "total", self.net_pay))
                
            # Update rounded net pay if applicable
            if hasattr(self, "rounded_net_pay"):
                self.rounded_net_pay = round(self.net_pay)
                
            # Update total in words if applicable
            if hasattr(self, "total_in_words") and hasattr(self, "total"):
                try:
                    from frappe.utils import money_in_words
                    currency = getattr(self, "currency", "IDR")
                    self.total_in_words = money_in_words(getattr(self, "total", 0), currency)
                except ImportError:
                    pass
                    
            # Update net pay in words if applicable
            if hasattr(self, "net_pay_in_words"):
                try:
                    from frappe.utils import money_in_words
                    currency = getattr(self, "currency", "IDR")
                    self.net_pay_in_words = money_in_words(self.net_pay, currency)
                except ImportError:
                    pass
                    
        except Exception as e:
            # Rounding/words conversion errors aren't critical to slip validity
            logger.warning(f"Failed to update rounded values for {self.name}: {str(e)}")

    def validate(self):
        """Ensure PPh 21 deduction row updated before saving."""
        try:
            # Try to run parent validation
            try:
                super().validate()
            except frappe.ValidationError as ve:
                # Let validation errors propagate up
                raise
            except Exception as e:
                error_trace = traceback.format_exc()
                frappe.log_error(
                    message=f"Error in parent validate for Salary Slip {self.name}: {str(e)}\n{error_trace}",
                    title="Payroll Indonesia Validation Error"
                )
                # We continue because we want to calculate tax even if base validation fails
                # This allows our tax calculation to run in environments where the parent
                # class might be different or missing certain methods

            # Calculate PPh21 based on tax type
            if getattr(self, "tax_type", "") == "DECEMBER":
                tax_amount = self.calculate_income_tax_december()
            else:
                tax_amount = self.calculate_income_tax()
                
            self.update_pph21_row(tax_amount)
            logger.info(f"Validate: Updated PPh21 deduction row to {tax_amount}")
            
        except frappe.ValidationError as ve:
            # Expected validation errors from tax calculations - re-raise to stop processing
            raise
            
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Failed to update PPh21 in validate for Salary Slip {self.name}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia PPh21 Update Error"
            )
            # Re-raise to prevent saving a slip with incorrect tax calculation
            raise frappe.ValidationError(f"Error calculating PPh21: {str(e)}")

    # -------------------------
    # Annual Payroll History sync
    # -------------------------
    def sync_to_annual_payroll_history(self, result, mode="monthly"):
        """Sync slip result to Annual Payroll History."""
        # Prevent duplicate sync when validate() is called multiple times
        if getattr(self, "_annual_history_synced", False):
            return

        try:
            # Check if employee exists
            if not hasattr(self, "employee") or not self.employee:
                logger.warning(
                    f"No employee found for Salary Slip {getattr(self, 'name', 'unknown')}, skipping sync"
                )
                return

            fiscal_year = getattr(self, "fiscal_year", None) or str(
                getattr(self, "start_date", None) or ""
            )[:4]
            if not fiscal_year:
                logger.warning(
                    f"Could not determine fiscal year for Salary Slip {self.name}, skipping sync"
                )
                return

            # Ambil nomor bulan menggunakan helper
            nomor_bulan = self._get_bulan_number(
                start_date=getattr(self, "start_date", None),
                nama_bulan=getattr(self, "bulan", None)
            )

            # Ensure numeric rate for Annual Payroll History child
            raw_rate = result.get("rate", 0)
            numeric_rate = raw_rate if isinstance(raw_rate, (int, float)) else 0
            monthly_result = {
                "bulan": nomor_bulan,
                "bruto": result.get("bruto", result.get("bruto_total", 0)),
                "pengurang_netto": result.get(
                    "pengurang_netto", result.get("income_tax_deduction_total", 0)
                ),
                "biaya_jabatan": result.get("biaya_jabatan", result.get("biaya_jabatan_total", 0)),
                "netto": result.get("netto", result.get("netto_total", 0)),
                "pkp": result.get("pkp", result.get("pkp_annual", 0)),
                "rate": flt(numeric_rate),
                "pph21": result.get("pph21", result.get("pph21_bulan", 0)),
                "salary_slip": self.name,
            }

            docname = None
            if mode == "monthly":
                docname = sync_annual_payroll_history(
                    employee=self.employee,
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
                # Preserve slab string separately for reporting if available
                if isinstance(raw_rate, str) and raw_rate:
                    summary["rate_slab"] = raw_rate
                docname = sync_annual_payroll_history(
                    employee=self.employee,
                    fiscal_year=fiscal_year,
                    monthly_results=[monthly_result],
                    summary=summary,
                )
            if docname:
                self._annual_history_synced = True
        except frappe.ValidationError as ve:
            # Let validation errors propagate as they indicate data problems
            raise
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Failed to sync Annual Payroll History for {getattr(self, 'name', 'unknown')}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia Annual History Sync Error"
            )
            # History sync failures shouldn't stop slip creation, so we log but don't raise
            logger.warning(f"Annual Payroll History sync failed for {self.name}: {str(e)}")

    def on_submit(self):
        """Sync Annual Payroll History after the Salary Slip is submitted."""
        try:
            info = json.loads(getattr(self, "pph21_info", "{}") or "{}")
        except Exception:
            info = {}
        mode = "december" if getattr(self, "tax_type", "") == "DECEMBER" else "monthly"
        self.sync_to_annual_payroll_history(info, mode=mode)
        if getattr(self, "_annual_history_synced", False):
            frappe.logger().info(
                f"[SYNC] Salary Slip {self.name} synced to Annual Payroll History for {self.employee}"
            )

    def on_cancel(self):
        """When slip is cancelled, remove related row from Annual Payroll History."""
        try:
            # Check if employee exists
            if not hasattr(self, "employee") or not self.employee:
                logger.warning(
                    f"No employee found for cancelled Salary Slip {getattr(self, 'name', 'unknown')}, skipping sync"
                )
                return

            fiscal_year = (
                getattr(self, "fiscal_year", None) or str(getattr(self, "start_date", ""))[:4]
            )
            if not fiscal_year:
                logger.warning(
                    f"Could not determine fiscal year for cancelled Salary Slip {self.name}, skipping sync"
                )
                return

            sync_annual_payroll_history(
                employee=self.employee,
                fiscal_year=fiscal_year,
                monthly_results=None,
                summary=None,
                cancelled_salary_slip=self.name,
            )
            frappe.logger().info(
                f"[SYNC] Salary Slip {self.name} removed from Annual Payroll History for {self.employee}"
            )
        except frappe.ValidationError as ve:
            # Pass through validation errors
            raise
        except Exception as e:
            error_trace = traceback.format_exc()
            frappe.log_error(
                message=f"Failed to remove from Annual Payroll History on cancel for {getattr(self, 'name', 'unknown')}: {str(e)}\n{error_trace}",
                title="Payroll Indonesia Annual History Cancel Error"
            )
            # History sync failures shouldn't stop slip cancellation, so we log but don't raise
            logger.warning(
                f"Failed to update Annual Payroll History when cancelling {self.name}: {str(e)}"
            )


def on_submit(doc, method=None):
    """DocEvent wrapper to sync Annual Payroll History on submit."""
    if isinstance(doc, CustomSalarySlip):
        return

    doc.__class__ = CustomSalarySlip
    doc.on_submit()


def on_cancel(doc, method=None):
    """DocEvent wrapper to clean up Annual Payroll History on cancel."""
    if isinstance(doc, CustomSalarySlip):
        return

    doc.__class__ = CustomSalarySlip
    doc.on_cancel()
