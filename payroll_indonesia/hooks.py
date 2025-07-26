app_name = "payroll_indonesia"
app_title = "Payroll Indonesia"
app_publisher = "IMOGI"
app_description = "Payroll Indonesia - Modul Perhitungan BPJS & PPh 21 untuk ERPNext Indonesia"
app_email = "hello@imogi.tech"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/payroll_indonesia/css/payroll_indonesia.css"
# app_include_js = "/assets/payroll_indonesia/js/payroll_indonesia.js"

# include js, css files in header of web template
# web_include_css = "/assets/payroll_indonesia/css/payroll_indonesia.css"
# web_include_js = "/assets/payroll_indonesia/js/payroll_indonesia.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "payroll_indonesia/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
#	"methods": "payroll_indonesia.utils.jinja_methods",
#	"filters": "payroll_indonesia.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "payroll_indonesia.install.before_install"
# after_install = "payroll_indonesia.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "payroll_indonesia.uninstall.before_uninstall"
# after_uninstall = "payroll_indonesia.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps.
#
# `after_sync` is executed immediately after DocType sync while
# `after_migrate` runs later once all patches have been applied.
# Running both hooks would call the setup twice, so we only use
# `after_migrate`.
after_migrate = [
    "payroll_indonesia.setup.setup_module.after_sync"
]

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "payroll_indonesia.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
#	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
#	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
#	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
#	"*": {
#		"on_update": "method",
#		"on_cancel": "method",
#		"on_trash": "method"
#	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
#	"all": [
#		"payroll_indonesia.tasks.all"
#	],
#	"daily": [
#		"payroll_indonesia.tasks.daily"
#	],
#	"hourly": [
#		"payroll_indonesia.tasks.hourly"
#	],
#	"weekly": [
#		"payroll_indonesia.tasks.weekly"
#	],
#	"monthly": [
#		"payroll_indonesia.tasks.monthly"
#	],
# }

# Testing
# -------

# before_tests = "payroll_indonesia.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
#	"frappe.desk.doctype.event.event.get_events": "payroll_indonesia.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
#	"Task": "payroll_indonesia.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["payroll_indonesia.utils.before_request"]
# after_request = ["payroll_indonesia.utils.after_request"]

# Job Events
# ----------
# before_job = ["payroll_indonesia.utils.before_job"]
# after_job = ["payroll_indonesia.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
#	{
#		"doctype": "{doctype_1}",
#		"filter_by": "{filter_by}",
#		"redact_fields": ["{field_1}", "{field_2}"],
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_2}",
#		"filter_by": "{filter_by}",
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_3}",
#		"strict": False,
#	},
#	{
#		"doctype": "{doctype_4}"
#	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
#	"payroll_indonesia.auth.validate"
# ]

# Fixtures
# --------
# Fixtures are data that should be auto-imported when the app is installed
fixtures = [
    "Custom Field",
    "Salary Component",
    "Income Tax Slab",
    "PTKP Table",
    "TER Bracket Table",
    "TER Mapping Table",
    "Payroll Indonesia Settings"
]