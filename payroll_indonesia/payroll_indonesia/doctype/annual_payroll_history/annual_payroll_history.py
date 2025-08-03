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
        pengurang_netto_total = 0
        biaya_jabatan_total = 0

        self.koreksi_pph21 = self.koreksi_pph21 or 0
        self.ptkp_annual = self.ptkp_annual or 0

        for row in self.monthly_details or []:
            bruto = flt(row.bruto)
            pengurang_netto = flt(getattr(row, "pengurang_netto", 0))
            biaya_jabatan = flt(getattr(row, "biaya_jabatan", 0))
            netto = flt(row.netto)

            pengurang_netto_total += pengurang_netto
            biaya_jabatan_total += biaya_jabatan

            calculated_netto = bruto - pengurang_netto - biaya_jabatan
            if abs(calculated_netto - netto) > 0.1:
                frappe.logger("payroll_indonesia").warning(
                    {
                        "message": "netto mismatch",
                        "calculated_netto": calculated_netto,
                        "stored_netto": netto,
                        "row": row.as_dict(),
                    }
                )

            totals["bruto_total"] += bruto
            totals["netto_total"] += netto
            totals["pkp_annual"] += flt(row.pkp)
            totals["pph21_annual"] += flt(row.pph21)

        self.update(totals)

        frappe.logger("payroll_indonesia").debug(
            {
                **totals,
                "pengurang_netto_total": pengurang_netto_total,
                "biaya_jabatan_total": biaya_jabatan_total,
                "koreksi_pph21": self.koreksi_pph21,
                "ptkp_annual": self.ptkp_annual,
            }
        )
