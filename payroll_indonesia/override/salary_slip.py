try:
    from erpnext.payroll.doctype.salary_slip.salary_slip import SalarySlip
except Exception:  # pragma: no cover - erpnext may not be installed during tests
    SalarySlip = object  # type: ignore

import frappe

from payroll_indonesia.config import pph21_ter, pph21_ter_december

class CustomSalarySlip(SalarySlip):
    """
    Salary Slip with Indonesian income tax calculations (TER bulanan dan Progressive/Desember).
    Koreksi PPh21 minus: PPh21 di slip minus, THP otomatis bertambah oleh sistem.
    """

    def calculate_income_tax(self):
        """
        Hitung pajak penghasilan sesuai mode payroll (TER atau Progressive/Desember).
        Koreksi PPh21 minus: komponen pajak di slip akan minus, THP otomatis bertambah.
        """
        # Mode: Progressive/Desember (final year/progressive)
        if getattr(self, "run_payroll_indonesia_december", False):
            frappe.logger().info("Salary Slip: calculating PPh21 December (progressive) mode.")
            employee_doc = self.get_employee_doc()
            # List slip gaji setahun (Jan-Des). Di payroll batch, harus diinject.
            salary_slips = getattr(self, "salary_slips_this_year", [self])
            # Total PPh21 Jan-Nov (harus diinject jika batch, 0 jika single slip)
            pph21_paid_jan_nov = getattr(self, "pph21_paid_jan_nov", 0)
            result = pph21_ter_december.calculate_pph21_TER_december(
                employee_doc,
                salary_slips,
                pph21_paid_jan_nov=pph21_paid_jan_nov
            )
            self.pph21_info = result
            koreksi_pph21 = result.get("koreksi_pph21", 0)
            self.tax = koreksi_pph21 if koreksi_pph21 > 0 else koreksi_pph21  # boleh minus
            self.tax_type = "DECEMBER"
            # Biarkan tax (komponen PPh21 di slip) minus jika kelebihan potong
            return self.tax

        # Mode: TER (bulanan/flat)
        if getattr(self, "run_payroll_indonesia", False):
            frappe.logger().info("Salary Slip: calculating PPh21 TER mode.")
            employee_doc = self.get_employee_doc()
            result = pph21_ter.calculate_pph21_TER(employee_doc, self)
            self.pph21_info = result
            self.tax = result.get("pph21", 0)
            self.tax_type = "TER"
            return self.tax

        # Default: fallback to vanilla ERPNext
        return super().calculate_income_tax()

    def get_employee_doc(self):
        """
        Helper: get employee doc/dict from self.employee (id, dict, or object).
        """
        if hasattr(self, "employee"):
            emp = self.employee
            if isinstance(emp, dict):
                return emp
            try:
                return frappe.get_doc("Employee", emp)
            except Exception:
                return {}
        return {}

    def as_dict(self):
        """
        Return a dict representation (for compatibility with PayrollEntry batch logic).
        """
        doc = super().as_dict() if hasattr(super(), "as_dict") else dict(self.__dict__)
        doc.update({
            "pph21_info": getattr(self, "pph21_info", {}),
            "tax": getattr(self, "tax", 0),
            "tax_type": getattr(self, "tax_type", None)
        })
        return doc