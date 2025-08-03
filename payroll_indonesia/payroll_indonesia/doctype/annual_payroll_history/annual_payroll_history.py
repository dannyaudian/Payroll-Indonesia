import frappe
from frappe.utils import flt
from frappe.model.document import Document

class AnnualPayrollHistory(Document):
    def validate(self):
        """
        Calculate totals from monthly details during validation.
        This ensures parent fields are always updated before saving.
        Applies formula: netto = bruto - pengurang_netto - biaya_jabatan
        """
        # Initialize totals
        self.bruto_total = 0
        self.netto_total = 0
        self.pkp_annual = 0
        self.pph21_annual = 0
        self.pengurang_netto_total = 0
        self.biaya_jabatan_total = 0

        # Process each monthly detail
        for row in self.monthly_details or []:
            # Get values with proper fallbacks
            bruto = flt(row.bruto)
            pengurang_netto = flt(getattr(row, "pengurang_netto", 0))
            biaya_jabatan = flt(getattr(row, "biaya_jabatan", 0))

            # Calculate expected netto based on the formula
            calculated_netto = bruto - pengurang_netto - biaya_jabatan
            stored_netto = flt(row.netto)

            # Log warning if there's a significant discrepancy between stored and calculated netto
            if abs(calculated_netto - stored_netto) > 0.1:
                frappe.logger("payroll_indonesia").warning(
                    f"Netto mismatch for month {row.bulan}: calculated={calculated_netto}, stored={stored_netto}, "
                    f"difference={calculated_netto - stored_netto}"
                )

            # Accumulate totals
            self.bruto_total += bruto
            self.netto_total += stored_netto
            self.pkp_annual += flt(row.pkp)
            self.pph21_annual += flt(row.pph21)
            self.pengurang_netto_total += pengurang_netto
            self.biaya_jabatan_total += biaya_jabatan

        # Set default values for required fields
        self.ptkp_annual = flt(self.ptkp_annual) or 0
        self.koreksi_pph21 = flt(self.koreksi_pph21) or 0
        self.rate = 0

        # Double-check the netto_total using the formula
        calculated_netto_total = self.bruto_total - self.pengurang_netto_total - self.biaya_jabatan_total
        if abs(calculated_netto_total - self.netto_total) > 1:
            frappe.logger("payroll_indonesia").warning(
                f"Total netto mismatch: calculated={calculated_netto_total}, stored={self.netto_total}, "
                f"difference={calculated_netto_total - self.netto_total}"
            )

        # Log debug information
        frappe.logger("payroll_indonesia").debug({
            "document": self.name,
            "bruto_total": self.bruto_total,
            "pengurang_netto_total": self.pengurang_netto_total,
            "biaya_jabatan_total": self.biaya_jabatan_total,
            "calculated_netto_total": calculated_netto_total,
            "stored_netto_total": self.netto_total,
            "pkp_annual": self.pkp_annual,
            "pph21_annual": self.pph21_annual,
            "koreksi_pph21": self.koreksi_pph21,
            "ptkp_annual": self.ptkp_annual,
        })
