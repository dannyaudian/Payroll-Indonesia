import frappe
from frappe.model.document import Document


class AnnualPayrollHistoryChild(Document):
    def get_title(self):
        return f"Bulan {self.bulan} - Netto {frappe.utils.fmt_money(self.netto)}"
