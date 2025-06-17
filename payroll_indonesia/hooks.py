# -*- coding: utf-8 -*-
# Copyright (c) 2025, PT. Innovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

# Basic app configuration
app_name = "payroll_indonesia"
app_title = "Payroll Indonesia"
app_publisher = "PT. Innovasi Terbaik Bangsa"
app_description = "Payroll module for Indonesian companies with local regulatory features"
app_email = "danny.a.pratama@cao-group.co.id"
app_license = "GPL-3"
app_version = "0.1.0"
required_apps = ["erpnext", "hrms"]

# Setup functions
before_install = "payroll_indonesia.install.before_install"
after_install = "payroll_indonesia.install.after_install"
# before_migrate = "payroll_indonesia.install.create_required_doctypes"
after_migrate = [
    "payroll_indonesia.install.after_migrate",
    # Panggil fungsi yang tidak memerlukan parameter
    "payroll_indonesia.fixtures.setup.setup_all_accounts",
]
# List view JS
doctype_list_js = {
    "BPJS Payment Summary": "payroll_indonesia/doctype/bpjs_payment_summary/bpjs_payment_summary_list.js",
    "Employee Tax Summary": "payroll_indonesia/public/js/employee_tax_summary_list.js",
    "BPJS Account Mapping": "payroll_indonesia/doctype/bpjs_account_mapping/bpjs_account_mapping_list.js",
}

# Document Events - primary hooks for document lifecycle
doc_events = {
    "Employee": {
        "validate": "payroll_indonesia.override.employee.validate",
        "on_update": "payroll_indonesia.override.employee.on_update",
    },
    "Payroll Entry": {
        "before_validate": "payroll_indonesia.override.payroll_entry_functions.before_validate"
    },
    "Salary Slip": {
        "validate": "payroll_indonesia.override.salary_slip_functions.validate_salary_slip",
        "on_submit": "payroll_indonesia.override.salary_slip_functions.on_submit_salary_slip",
        "on_cancel": "payroll_indonesia.override.salary_slip_functions.on_cancel_salary_slip",
        "after_insert": "payroll_indonesia.override.salary_slip_functions.after_insert_salary_slip",
    },
    "PPh 21 Settings": {
        "on_update": "payroll_indonesia.payroll_indonesia.tax.pph21_settings.on_update"
    },
    "BPJS Settings": {
        "validate": "payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings.validate",
        "on_update": "payroll_indonesia.payroll_indonesia.doctype.bpjs_settings.bpjs_settings.on_update",
    },
    "BPJS Account Mapping": {
        "validate": "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.validate",
        "on_update": "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.on_update",
    },
    # "BPJS Payment Component": {
    #     "validate": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_component.bpjs_payment_component.validate",
    #     "on_submit": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_component.bpjs_payment_component.on_submit",
    # },
    "BPJS Payment Summary": {
        "validate": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.validate",
        "on_submit": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.on_submit",
        "on_cancel": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_summary.on_cancel",
    },
    "Payment Entry": {
        "on_submit": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.payment_hooks.payment_entry_on_submit",
        "on_cancel": "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.payment_hooks.payment_entry_on_cancel",
    },
    "Account": {"on_update": "payroll_indonesia.payroll_indonesia.account_hooks.account_on_update"},
    "Company": {"after_insert": "payroll_indonesia.fixtures.setup.setup_company_accounts"},
}

# Fixtures - dengan filter sesuai dengan kebutuhan
fixtures = [
    {"doctype": "Custom Field", "filters": [["module", "=", "Payroll Indonesia"]]},
    {"doctype": "Property Setter", "filters": [["module", "=", "Payroll Indonesia"]]},
    {"doctype": "Client Script", "filters": [["module", "=", "Payroll Indonesia"]]},
    {"doctype": "Workspace", "filters": [["module", "=", "Payroll Indonesia"]]},
    {"doctype": "Report", "filters": [["module", "=", "Payroll Indonesia"]]},
    {"doctype": "Print Format", "filters": [["name", "in", ["BPJS Payment Summary Report"]]]},
    # {"doctype": "Doctype",  "filters": [["name", "in", ["BPJS Payment Summary","BPJS Payment Summary Detail"]]]},
    # Master Data
    {"doctype": "Supplier Group", "filters": [["name", "in", ["BPJS Provider", "Tax Authority"]]]},
    {
        "doctype": "Supplier",
        "filters": [["supplier_group", "in", ["BPJS Provider", "Tax Authority"]]],
    },
    {"doctype": "Tax Category", "filters": [["name", "like", "PPh 21%"]]},
    # Payroll Indonesia Settings
    {"doctype": "BPJS Settings", "filters": [["name", "=", "BPJS Settings"]]},
    {"doctype": "PPh 21 Settings", "filters": [["name", "=", "PPh 21 Settings"]]},
    {"doctype": "PPh 21 Tax Bracket", "filters": [["parent", "=", "PPh 21 Settings"]]},
    {"doctype": "PPh 21 PTKP", "filters": [["parent", "=", "PPh 21 Settings"]]},
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
    # Add fixtures for new DocTypes
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
                    "BPJS Payment Summary",
                    "BPJS Payment Summary Detail",
                ],
            ]
        ],
    },
]

# Scheduler tasks - Updated with correct paths and added cache clearing for salary_slip
scheduler_events = {
    "daily": [
        "payroll_indonesia.utilities.cache_utils.clear_all_caches",
        "payroll_indonesia.utilities.cache_utils.clear_salary_slip_caches",
    ],
    "cron": {
        "0 */4 * * *": ["payroll_indonesia.utilities.cache_utils.clear_all_caches"],
        "30 1 * * *": ["payroll_indonesia.utilities.cache_utils.clear_salary_slip_caches"],
    },
    "monthly": ["payroll_indonesia.payroll_indonesia.tax.monthly_tasks.update_tax_summaries"],
    "yearly": ["payroll_indonesia.payroll_indonesia.tax.yearly_tasks.prepare_tax_report"],
}

# Jinja template methods - only expose read-only and safe functions
jinja = {
    "methods": [
        # BPJS Settings & Functions
        "payroll_indonesia.payroll_indonesia.utils.get_bpjs_settings",
        "payroll_indonesia.payroll_indonesia.utils.calculate_bpjs_contributions",
        "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.get_mapping_for_company",
        "payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation.hitung_bpjs",
        # PPh 21 Settings & Functions
        "payroll_indonesia.payroll_indonesia.utils.get_ptkp_settings",
        "payroll_indonesia.payroll_indonesia.utils.get_ter_rate",
        "payroll_indonesia.payroll_indonesia.utils.should_use_ter",
        "payroll_indonesia.payroll_indonesia.utils.get_pph21_settings",
        "payroll_indonesia.payroll_indonesia.utils.get_pph21_brackets",
        # Tax Reporting Functions
        "payroll_indonesia.payroll_indonesia.utils.get_ytd_tax_info",
        "payroll_indonesia.payroll_indonesia.utils.get_spt_month",
        # Utility Functions
        "payroll_indonesia.override.salary_slip.base.get_formatted_currency",
        "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_utils.get_formatted_currency",
    ]
}

# Hook to initialize module functionality after app startup
after_app_init = "payroll_indonesia.override.salary_slip.setup_hooks"

# Whitelist for client-side API calls
whitelist_methods = [
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.create_payment_entry",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_employee_bpjs_details",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_summary_for_period",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_payment_summary.bpjs_payment_api.get_bpjs_suppliers",
    "payroll_indonesia.payroll_indonesia.doctype.employee_tax_summary.employee_tax_summary.get_ytd_data_until_month",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.get_mapping_for_company",
    "payroll_indonesia.payroll_indonesia.doctype.bpjs_account_mapping.bpjs_account_mapping.create_default_mapping",
    "payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation.update_all_bpjs_components",
    "payroll_indonesia.payroll_indonesia.bpjs.bpjs_calculation.hitung_bpjs",
    "payroll_indonesia.api.diagnose_salary_slip",
    "payroll_indonesia.api.get_employee",
    "payroll_indonesia.api.get_salary_slips_by_employee",
    "payroll_indonesia.api.get_salary_slip",
    "payroll_indonesia.api.get_recent_salary_slips",
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
