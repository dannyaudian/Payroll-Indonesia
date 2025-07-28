from frappe.model.document import Document

class AnnualPayrollHistory(Document):
    def validate(self):
        # Inisialisasi total
        self.total_bruto = 0
        self.total_pengurang_netto = 0
        self.total_biaya_jabatan = 0
        self.total_netto = 0
        self.total_pkp = 0
        self.total_pph21 = 0

        # Penjumlahan dari child table
        for row in self.monthly_details:
            self.total_bruto += row.bruto or 0
            self.total_pengurang_netto += row.pengurang_netto or 0
            self.total_biaya_jabatan += row.biaya_jabatan or 0
            self.total_netto += row.netto or 0
            self.total_pkp += row.pkp or 0
            self.total_pph21 += row.pph21 or 0
