# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PTKPTERMappingEntry(Document):
    def validate(self):
        """Validate PTKP TER Mapping Entry"""
        self.validate_ptkp_status()

    def validate_ptkp_status(self):
        """Validate PTKP status format if possible"""
        if self.ptkp_status:
            # Basic format validation (e.g., TK0, K1, etc.)
            valid_prefixes = ["TK", "K", "HB"]

            # Extract prefix (first 2 characters or 1 if only 1 character)
            prefix = self.ptkp_status[:2] if len(self.ptkp_status) >= 2 else self.ptkp_status

            if prefix not in valid_prefixes:
                frappe.msgprint(
                    frappe._(
                        "PTKP Status '{0}' has an unusual format. Expected prefix: TK, K, or HB"
                    ).format(self.ptkp_status),
                    indicator="orange",
                )

            # Check if there's a number after the prefix
            if len(self.ptkp_status) > 2:
                suffix = self.ptkp_status[2:]
                if not suffix.isdigit():
                    frappe.msgprint(
                        frappe._(
                            "PTKP Status '{0}' has an unusual format. Expected numeric suffix"
                        ).format(self.ptkp_status),
                        indicator="orange",
                    )
