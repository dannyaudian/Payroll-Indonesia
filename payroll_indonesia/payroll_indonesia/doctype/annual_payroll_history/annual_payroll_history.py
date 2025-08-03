import frappe
from frappe.utils import flt
from frappe.model.document import Document

class AnnualPayrollHistory(Document):
    def validate(self):
        self.calculate_totals()

    def calculate_totals(self):
        totals = {
            "bruto_total": 0,
            "netto_total": 0,
            "pkp_annual": 0,
            "pph21_annual": 0,
        }

        self.koreksi_pph21 = self.koreksi_pph21 or 0
        self.ptkp_annual = self.ptkp_annual or 0

        for row in self.monthly_details or []:
            totals["bruto_total"] += flt(row.bruto)
            totals["netto_total"] += flt(row.netto)
            totals["pkp_annual"] += flt(row.pkp)
            totals["pph21_annual"] += flt(row.pph21)

        self.update(totals)

        frappe.logger("payroll_indonesia").debug(
            {
                **totals,
                "koreksi_pph21": self.koreksi_pph21,
                "ptkp_annual": self.ptkp_annual,
            }
        )
