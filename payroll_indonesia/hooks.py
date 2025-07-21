# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt
# Last modified: 2025-07-02 16:03:46 by dannyaudian

from __future__ import unicode_literals

# ❶ Basic app configuration
app_name = "payroll_indonesia"
app_title = "Payroll Indonesia"
app_publisher = "PT. Innovasi Terbaik Bangsa"
app_description = "Payroll module for Indonesian companies with local regulations"
app_email = "danny.a.pratama@cao-group.co.id"
app_icon = "octicon octicon-file-directory"
app_license = "MIT"
app_version = "0.1.0"
required_apps = ["erpnext", "hrms"]

# ❷ Install hooks
before_install = "payroll_indonesia.fixtures.setup.before_install"
after_install = "payroll_indonesia.fixtures.setup.after_install"
after_sync = "payroll_indonesia.fixtures.setup.after_sync"
after_migrate = [
    "payroll_indonesia.setup.setup_module.after_migrate"  # Use our new after_migrate function
]

# List view JS
doctype_list_js = {
    "BPJS Payment Summary": "payroll_indonesia/doctype/bpjs_payment_summary/bpjs_payment_summary_list.js",
    "Employee Tax Summary": "payroll_indonesia/public/js/employee_tax_summary_list.js",
    "BPJS Account Mapping": "payroll_indonesia/doctype/bpjs_account_mapping/bpjs_account_mapping_list.js",
}

# ❹ Document Events - primary hooks for document lifecycle
doc_events = {
    "Employee": {
        "validate": "payroll_indonesia.override.employee.validate",
        "on_update": "payroll_indonesia.override.employee.on_update",
    },
    "Salary Slip": {
        "before_validate": "payroll_indonesia.override.salary_slip_functions.before_validate",
        "validate": "payroll_indonesia.override.salary_slip_functions.validate",
        "before_save": "payroll_indonesia.override.salary_slip_functions.before_save",
        "after_save": "payroll_indonesia.override.salary_slip_functions.after_save",
        "on_cancel": "payroll_indonesia.override.salary_slip_functions.on_cancel",
        "after_submit": "payroll_indonesia.override.salary_slip_functions.after_submit",
    },
    "BPJS Account Mapping": {
        "validate": "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.validate",
        "on_update": "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.on_update",
    },
    "BPJS Payment Summary": {
        "validate": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.validate",
        "on_submit": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.on_submit",
        "on_cancel": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.on_cancel",
    },
    "Company": {
        # on_update is triggered on both insert and update events
        "on_update": "payroll_indonesia.fixtures.setup.setup_company",
    },
    "Payment Entry": {
        "on_submit": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.payment_hooks.on_payment_entry_submit",
    },
    "Payroll Entry": {
        "before_validate": "payroll_indonesia.override.payroll_entry_functions.before_validate",
        "validate": "payroll_indonesia.override.payroll_entry_functions.validate",
        "before_submit": "payroll_indonesia.override.payroll_entry_functions.before_submit",
        "on_submit": "payroll_indonesia.override.payroll_entry_functions.on_submit",
        "after_submit": "payroll_indonesia.override.payroll_entry_functions.after_submit",
    },
}

# ❸ Override DocType classes
override_doctype_class = {
    "Salary Slip": "payroll_indonesia.override.salary_slip.controller.IndonesiaPayrollSalarySlip",
    "Payroll Entry": "payroll_indonesia.override.payroll_entry.CustomPayrollEntry",
    "Employee": "payroll_indonesia.override.employee.EmployeeOverride",
}

# Fixtures - dengan filter sesuai dengan kebutuhan
fixtures = [
    {"doctype": "Property Setter", "filters": [["module", "=", "Payroll Indonesia"]]},
    {"doctype": "Client Script", "filters": [["module", "=", "Payroll Indonesia"]]},
    {"doctype": "Workspace", "filters": [["module", "=", "Payroll Indonesia"]]},
    {"doctype": "Report", "filters": [["module", "=", "Payroll Indonesia"]]},
    {"doctype": "Print Format", "filters": [["name", "in", ["BPJS Payment Summary Report"]]]},
    # Master Data
    {"doctype": "Supplier Group", "filters": [["name", "in", ["BPJS Provider", "Tax Authority"]]]},
    {
        "doctype": "Supplier",
        "filters": [["supplier_group", "in", ["BPJS Provider", "Tax Authority"]]],
    },
    {"doctype": "Tax Category", "filters": [["name", "like", "PPh 21%"]]},
    # Payroll Indonesia Settings and Child Tables
    {
        "doctype": "Payroll Indonesia Settings",
        "filters": [["name", "=", "Payroll Indonesia Settings"]],
    },
    {"doctype": "PTKP Table Entry", "filters": [["parent", "=", "Payroll Indonesia Settings"]]},
    {
        "doctype": "PTKP TER Mapping Entry",
        "filters": [["parent", "=", "Payroll Indonesia Settings"]],
    },
    {"doctype": "Tax Bracket Entry", "filters": [["parent", "=", "Payroll Indonesia Settings"]]},
    {"doctype": "Tipe Karyawan Entry", "filters": [["parent", "=", "Payroll Indonesia Settings"]]},
    {"doctype": "PPh 21 TER Table", "filters": [["status_pajak", "like", "TER %"]]},
    # BPJS Account Mappings
    {"doctype": "BPJS Account Mapping", "filters": [["company", "like", "%"]]},
    # Salary Components
    {
        "doctype": "Salary Component",
        "filters": [
            [
                "name",
                "in",
                [
                    "BPJS Kesehatan Employee",
                    "BPJS Kesehatan Employer",
                    "BPJS JHT Employee",
                    "BPJS JHT Employer",
                    "BPJS JP Employee",
                    "BPJS JP Employer",
                    "BPJS JKK",
                    "BPJS JKM",
                    "PPh 21",
                ],
            ]
        ],
    },
    # Master Data - Payroll
    {"doctype": "Golongan", "filters": [["name", "like", "%"]]},
    {"doctype": "Jabatan", "filters": [["name", "like", "%"]]},
    # Add DocTypes
    {
        "doctype": "DocType",
        "filters": [
            [
                "name",
                "in",
                [
                    "Payroll Indonesia Settings",
                    "PTKP Table Entry",
                    "PTKP TER Mapping Entry",
                    "Tax Bracket Entry",
                    "Tipe Karyawan Entry",
                    "PPh 21 TER Table",
                    "BPJS Payment Summary",
                    "BPJS Payment Summary Detail",
                ],
            ]
        ],
    },
]

# ❺ Scheduler tasks
scheduler_events = {
    "daily": ["payroll_indonesia.scheduler.tasks.daily_job"],
    "monthly": ["payroll_indonesia.scheduler.tasks.monthly_job"],
    "yearly": ["payroll_indonesia.scheduler.tasks.yearly_job"],
    "cron": {
        "0 */4 * * *": ["payroll_indonesia.scheduler.tasks.clear_caches"],
        "30 1 * * *": ["payroll_indonesia.scheduler.tasks.cleanup_logs"],
    },
}

# ❻ Authentication hooks
authentication_hooks = "payroll_indonesia.override.auth_hooks.validate_login"

# ❼ Jinja template methods - only expose read-only and safe functions
jinja = {
    "methods": [
        # Configuration and Utils
        "payroll_indonesia.config.config.get_live_config",
        # Tax calculation methods
        "payroll_indonesia.override.salary_slip.tax_calculator.get_ptkp_value",
        "payroll_indonesia.payroll_indonesia.utils.get_ter_rate_for_template",
        # BPJS methods
        "payroll_indonesia.override.salary_slip.bpjs_calculator.calculate_components",
        "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.get_mapping_for_company",
        # YTD methods
        "payroll_indonesia.override.salary_slip.salary_utils.calculate_ytd_and_ytm",
    ]
}

# Whitelist for client-side API calls
whitelist_methods = [
    # BPJS Payment API
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.create_payment_entry",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_employee_bpjs_details",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_summary_for_period",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_bpjs_suppliers",
    # Tax Summary API
    "payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.get_ytd_data_until_month",
    # BPJS Account API
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.get_mapping_for_company",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.create_default_mapping",
    # API endpoints
    "payroll_indonesia.api.get_employee",
    "payroll_indonesia.api.get_salary_slip",
    "payroll_indonesia.api.get_salary_slips_by_employee",
    "payroll_indonesia.api.get_recent_salary_slips",
    "payroll_indonesia.api.diagnose_salary_slip",
    "payroll_indonesia.api.calculate_bpjs",
    "payroll_indonesia.api.calculate_tax",
]

# Override whitelisted methods
override_whitelisted_methods = {
    "hrms.payroll.doctype.salary_slip.salary_slip.make_salary_slip_from_timesheet": "payroll_indonesia.override.salary_slip.make_salary_slip_from_timesheet"
}

# Module Category - for Desk
module_categories = {"Payroll Indonesia": "Human Resources"}

# Web Routes
website_route_rules = [
    {
        "from_route": "/payslip/<path:payslip_name>",
        "to_route": "payroll_indonesia/templates/pages/payslip",
    }
]
