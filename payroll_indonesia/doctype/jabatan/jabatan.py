# Copyright (c) 2023, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Jabatan(Document):
    def validate(self):
        self.validate_employee_golongan_levels()

    def validate_employee_golongan_levels(self):
        """
        Validate that all employees assigned to this position have golongan levels
        less than or equal to the maximum allowed level for this position
        """
        if not self.max_golongan:
            return

        max_level = frappe.db.get_value("Golongan", self.max_golongan, "level")
        if not max_level:
            return

        # Get all employees with this position
        employees = frappe.get_all(
            "Employee",
            filters={"designation": self.name},
            fields=["name", "employee_name", "golongan"],
        )

        for employee in employees:
            if not employee.golongan:
                continue

            employee_level = frappe.db.get_value("Golongan", employee.golongan, "level")
            if employee_level and employee_level > max_level:
                frappe.throw(
                    _(
                        "Employee {0} ({1}) has Golongan level {2} which is higher than "
                        "the maximum allowed level {3} for this position"
                    ).format(employee.name, employee.employee_name, employee_level, max_level)
                )
