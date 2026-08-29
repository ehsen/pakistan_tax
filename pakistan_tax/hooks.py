app_name = "pakistan_tax"
app_title = "Pakistan Tax Compliance"
app_publisher = "SpotLedger"
app_description = "End-to-end Pakistan tax compliance for ERPNext - FBR Digital Invoicing, native tax engine configuration, WHT, party-level tax reconciliation"
app_email = "ehsensiraj@gmail.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "pakistan_tax",
# 		"logo": "/assets/pakistan_tax/logo.png",
# 		"title": "Pakistan Tax Compliance",
# 		"route": "/pakistan_tax",
# 		"has_permission": "pakistan_tax.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/pakistan_tax/css/pakistan_tax.css"
app_include_js = "/assets/pakistan_tax/js/tax_row_direction.js"

# Boot
# ----
extend_bootinfo = "pakistan_tax.boot.boot_session"

# include js, css files in header of web template
# web_include_css = "/assets/pakistan_tax/css/pakistan_tax.css"
# web_include_js = "/assets/pakistan_tax/js/pakistan_tax.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "pakistan_tax/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Sales Invoice": "public/js/sales_invoice_fbr.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "pakistan_tax/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "pakistan_tax.utils.jinja_methods",
# 	"filters": "pakistan_tax.utils.jinja_filters"
# }

# Installation
# ------------

before_install = "pakistan_tax.setup.install.before_install"
after_install = "pakistan_tax.setup.install.after_install"
after_migrate = "pakistan_tax.setup.install.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "pakistan_tax.uninstall.before_uninstall"
# after_uninstall = "pakistan_tax.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "pakistan_tax.utils.before_app_install"
# after_app_install = "pakistan_tax.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "pakistan_tax.utils.before_app_uninstall"
# after_app_uninstall = "pakistan_tax.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "pakistan_tax.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Sales Invoice": {
		"before_validate": [
			"pakistan_tax.transactions.resolution.resolve_templates",
			"pakistan_tax.transactions.fixed_component.apply_fixed_components",
		],
		"validate": "pakistan_tax.transactions.line_taxes.update_line_tax_fields",
		"before_submit": [
			"pakistan_tax.transactions.submit.validate_and_snapshot",
			"pakistan_tax.pra.controller.before_submit",
		],
		"on_submit": [
			"pakistan_tax.tax_ledger.posting.on_invoice_submit",
			"pakistan_tax.tax_ledger.gl_party.stamp_tax_gl_party",
		],
		"on_cancel": "pakistan_tax.tax_ledger.posting.on_voucher_cancel",
	},
	"Purchase Invoice": {
		"before_validate": [
			"pakistan_tax.transactions.resolution.resolve_templates",
			"pakistan_tax.transactions.fixed_component.apply_fixed_components",
		],
		"validate": [
			"pakistan_tax.transactions.line_taxes.update_line_tax_fields",
			"pakistan_tax.transactions.supplier_tax_reconciliation.reconcile_supplier_tax",
		],
		"before_submit": "pakistan_tax.transactions.submit.validate_and_snapshot",
		"on_submit": [
			"pakistan_tax.tax_ledger.posting.on_invoice_submit",
			"pakistan_tax.tax_ledger.gl_party.stamp_tax_gl_party",
		],
		"on_cancel": "pakistan_tax.tax_ledger.posting.on_voucher_cancel",
	},
	"Payment Entry": {
		"before_validate": "pakistan_tax.wht.payment_entry.calculate_wht",
		"on_submit": "pakistan_tax.tax_ledger.posting.on_payment_submit",
		"on_cancel": "pakistan_tax.tax_ledger.posting.on_voucher_cancel",
	},
	"Item": {
		"validate": "pakistan_tax.transactions.third_schedule.sync_third_schedule_template",
	},
	"Landed Cost Voucher": {
		"on_submit": "pakistan_tax.tax_ledger.import_posting.on_lcv_submit",
		"on_cancel": "pakistan_tax.tax_ledger.posting.on_voucher_cancel",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"pakistan_tax.fbr.sync.daily_sync",
		"pakistan_tax.pakistan_tax_compliance.doctype.sro_applicability.sro_applicability.apply_all",
	],
}

# Testing
# -------

# before_tests = "pakistan_tax.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "pakistan_tax.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "pakistan_tax.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "pakistan_tax.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["pakistan_tax.utils.before_request"]
# after_request = ["pakistan_tax.utils.after_request"]

# Job Events
# ----------
# before_job = ["pakistan_tax.utils.before_job"]
# after_job = ["pakistan_tax.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"pakistan_tax.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

