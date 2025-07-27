from erpnext.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry
import frappe
from payroll_indonesia.config import config

class CustomPayrollEntry(PayrollEntry):
    def validate(self):
        super().validate()
        # Custom validation or field set logic for Payroll Indonesia
        if getattr(self, "run_payroll_indonesia", False):
            frappe.logger().info("Payroll Entry: Run Payroll Indonesia is checked.")
            settings = config.get_settings()
            if hasattr(self, "pph21_method") and not self.pph21_method:
                self.pph21_method = settings.get("pph21_method", "TER")
        
        # Tidak perlu cek bulan, cukup cek flag run_payroll_indonesia_december
        if getattr(self, "run_payroll_indonesia_december", False):
            frappe.logger().info("Payroll Entry: Run Payroll Indonesia DECEMBER mode is checked.")
            # Di sini nanti bisa tambahkan validasi/logic khusus Desember jika diperlukan

    def create_salary_slips(self):
        # Jika December mode, jalankan logic khusus Desember
        if getattr(self, "run_payroll_indonesia_december", False):
            frappe.logger().info("Payroll Entry: Running custom Salary Slip generation for Payroll Indonesia DECEMBER mode.")
            # TODO: Implementasikan perhitungan payroll Indonesia Desember di sini
            # Contoh: slips = payroll_indonesia.custom_salary_slip_december_logic(self)
            # return slips
            return super().create_salary_slips()
        # Jika mode Indonesia biasa
        elif getattr(self, "run_payroll_indonesia", False):
            frappe.logger().info("Payroll Entry: Running custom Salary Slip generation for Payroll Indonesia.")
            # TODO: Implementasikan perhitungan payroll Indonesia normal di sini
            # Contoh: slips = payroll_indonesia.custom_salary_slip_logic(self)
            # return slips
            return super().create_salary_slips()
        else:
            return super().create_salary_slips()