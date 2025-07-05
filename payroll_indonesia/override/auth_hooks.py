# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-05-11 08:09:23 by dannyaudian

import frappe


def on_session_creation(login_manager):
    """Hook that runs when a new session is created"""

    # Check if session user is in Indonesia
    user = frappe.session.user
    if not user or user == "Guest":
        return

    try:
        # Get the employee linked to this user
        employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
        if not employee:
            return

        # Get company of this employee
        company = frappe.db.get_value("Employee", employee, "company")
        if not company:
            return

        # Get company country
        country = frappe.db.get_value("Company", company, "country")

        # If company is in Indonesia, set regional settings
        if country == "Indonesia":
            # Add this information to the session
            if hasattr(frappe.local, "session"):
                frappe.local.session.data.payroll_region = "Indonesia"

            # Log access in a safe way
            frappe.log_error(
                "User {0} (Employee: {1}) logged in - Region Indonesia".format(user, employee),
                "Region-specific Login",
            )

    except Exception as e:
        # This is non-critical - log error but allow login to continue
        frappe.log_error(
            "Error in session creation hook for user {0}: {1}".format(
                user if user else "Unknown", str(e)
            ),
            "Auth Hook Error",
        )
        # No msgprint here as it would disrupt the login flow
