from frappe.model.document import Document

class AnnualPayrollHistory(Document):
    def validate(self):
        # Inisialisasi total
        self.bruto_total = 0
        self.netto_total = 0
        self.pkp_annual = 0
        self.pph21_annual = 0

        # Penjumlahan dari child table
        for row in self.monthly_details:
            self.bruto_total += row.bruto or 0
            self.netto_total += row.netto or 0
            self.pkp_annual += row.pkp or 0
            self.pph21_annual += row.pph21 or 0
