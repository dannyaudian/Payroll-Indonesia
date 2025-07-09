# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-04-23 11:45:37 by dannyaudian

from __future__ import unicode_literals
from frappe.model.document import Document
from frappe.utils import now


class PayrollLog(Document):
    def validate(self):
        """Validate Payroll Log entry"""
        if not self.log_time:
            self.log_time = now()

        if not self.title:
            self.set_title()

    def set_title(self):
        """Set document title"""
        self.title = f"{self.employee_name} - {self.posting_date}"
