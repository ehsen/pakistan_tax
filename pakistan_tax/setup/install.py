# Copyright (c) 2026, SpotLedger
"""Install-time setup: custom fields owned by pakistan_tax.

All custom fields this app needs live here (created via after_install /
after_migrate) so nothing exists only in a site database.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "Pakistan Tax Compliance"

TAX_CATEGORY_OPTIONS = "\nSales Tax\nSales Tax Fixed\nFurther Sales Tax\nAdvance Tax 236G\nWHT"

CUSTOM_FIELDS = {
	"UOM": [
		{
			"fieldname": "custom_is_fbr_uom",
			"fieldtype": "Check",
			"label": "Is FBR UOM",
			"insert_after": "enabled",
			"read_only": 1,
			"module": MODULE,
		},
		{
			"fieldname": "custom_fbr_uom_id",
			"fieldtype": "Int",
			"label": "FBR UOM ID",
			"insert_after": "custom_is_fbr_uom",
			"read_only": 1,
			"module": MODULE,
		},
	],
	"Item Tax Template": [
		{
			"fieldname": "pk_fbr_section",
			"fieldtype": "Section Break",
			"label": "FBR",
			"insert_after": "disabled",
			"module": MODULE,
		},
		{
			"fieldname": "pk_fbr_transaction_type",
			"fieldtype": "Link",
			"options": "FBR Transaction Type",
			"label": "FBR Transaction Type",
			"insert_after": "pk_fbr_section",
			"module": MODULE,
		},
		{
			"fieldname": "pk_fbr_rate",
			"fieldtype": "Link",
			"options": "FBR Rate",
			"label": "FBR Rate",
			"insert_after": "pk_fbr_transaction_type",
			"module": MODULE,
		},
		{
			"fieldname": "pk_fbr_rate_description",
			"fieldtype": "Data",
			"label": "FBR Rate Description",
			"fetch_from": "pk_fbr_rate.rate_desc",
			"read_only": 1,
			"insert_after": "pk_fbr_rate",
			"module": MODULE,
		},
		{
			"fieldname": "pk_is_fbr_generated",
			"fieldtype": "Check",
			"label": "FBR Generated (immutable)",
			"read_only": 1,
			"insert_after": "pk_fbr_rate_description",
			"module": MODULE,
		},
	],
	"Item Tax Template Detail": [
		{
			"fieldname": "pk_tax_category",
			"fieldtype": "Select",
			"options": TAX_CATEGORY_OPTIONS,
			"label": "Pakistan Tax Category",
			"insert_after": "tax_rate",
			"in_list_view": 1,
			"module": MODULE,
		},
	],
	"Sales Taxes and Charges": [
		{
			"fieldname": "pk_tax_category",
			"fieldtype": "Select",
			"options": TAX_CATEGORY_OPTIONS,
			"label": "Pakistan Tax Category",
			"insert_after": "account_head",
			"module": MODULE,
		},
		{
			"fieldname": "pk_track_party_wise",
			"fieldtype": "Check",
			"label": "Track Party-wise",
			"description": "Stamp the document's party onto this row's GL entries "
				"(account-level flag on the Account also enables this)",
			"insert_after": "pk_tax_category",
			"module": MODULE,
		},
	],
	"Purchase Taxes and Charges": [
		{
			"fieldname": "pk_tax_category",
			"fieldtype": "Select",
			"options": TAX_CATEGORY_OPTIONS,
			"label": "Pakistan Tax Category",
			"insert_after": "account_head",
			"module": MODULE,
		},
		{
			"fieldname": "pk_track_party_wise",
			"fieldtype": "Check",
			"label": "Track Party-wise",
			"description": "Stamp the document's party onto this row's GL entries "
				"(account-level flag on the Account also enables this)",
			"insert_after": "pk_tax_category",
			"module": MODULE,
		},
	],
	"Account": [
		{
			"fieldname": "pk_track_party_wise",
			"fieldtype": "Check",
			"label": "Track Party-wise (Pakistan Tax)",
			"description": "Tax rows posting to this account get the document's "
				"party stamped on their GL entries",
			"insert_after": "account_type",
			"module": MODULE,
		},
	],
}


def _line_tax_fields():
	"""Per-row tax output fields (§3.1) — populated by the engine via
	pakistan_tax.transactions.line_taxes, never entered by hand."""
	fields = [
		{"fieldname": "pk_tax_section", "fieldtype": "Section Break",
			"label": "Pakistan Tax", "insert_after": "amount", "collapsible": 0},
		{"fieldname": "pk_st_rate", "fieldtype": "Float", "label": "ST Rate (%)",
			"insert_after": "pk_tax_section"},
		{"fieldname": "pk_st_amount", "fieldtype": "Currency", "label": "ST Amount",
			"options": "currency", "insert_after": "pk_st_rate", "in_list_view": 0,
			"columns": 1},
		{"fieldname": "pk_further_tax_rate", "fieldtype": "Float",
			"label": "Further Tax Rate (%)", "insert_after": "pk_st_amount"},
		{"fieldname": "pk_tax_col_break", "fieldtype": "Column Break",
			"insert_after": "pk_further_tax_rate"},
		{"fieldname": "pk_further_tax_amount", "fieldtype": "Currency",
			"label": "Further Tax Amount", "options": "currency",
			"insert_after": "pk_tax_col_break"},
		{"fieldname": "pk_advance_tax_amount", "fieldtype": "Currency",
			"label": "Advance Tax Amount", "options": "currency",
			"insert_after": "pk_further_tax_amount"},
		{"fieldname": "pk_total_incl_tax", "fieldtype": "Currency",
			"label": "Total Incl. Tax", "options": "currency",
			"insert_after": "pk_advance_tax_amount", "columns": 1},
	]
	for f in fields:
		f["module"] = MODULE
		if f["fieldtype"] not in ("Section Break", "Column Break"):
			f["read_only"] = 1
			f["no_copy"] = 1
	return fields


def _row_fbr_fields():
	"""Row-level FBR inputs + frozen snapshots (§3.5/§3.6/§3.9)."""
	return [
		{"fieldname": "pk_fbr_transaction_type", "fieldtype": "Link",
			"options": "FBR Transaction Type", "label": "FBR Transaction Type",
			"insert_after": "item_tax_template", "fetch_from": "item_code.pk_fbr_transaction_type",
			"fetch_if_empty": 1},
		{"fieldname": "pk_sro_schedule", "fieldtype": "Link", "options": "FBR SRO",
			"label": "SRO Schedule", "insert_after": "pk_fbr_transaction_type"},
		{"fieldname": "pk_sro_item_serial", "fieldtype": "Data",
			"label": "SRO Item Serial", "insert_after": "pk_sro_schedule"},
		# frozen at submit — payload/reports read these, never re-resolve
		{"fieldname": "pk_fbr_rate", "fieldtype": "Link", "options": "FBR Rate",
			"label": "FBR Rate (snapshot)", "read_only": 1, "no_copy": 1,
			"insert_after": "pk_sro_item_serial"},
		{"fieldname": "pk_fbr_rate_desc", "fieldtype": "Data",
			"label": "FBR Rate Description (snapshot)", "read_only": 1, "no_copy": 1,
			"insert_after": "pk_fbr_rate"},
	]


def _party_status_fields(insert_after):
	return [
		{"fieldname": "pk_fbr_status_section", "fieldtype": "Section Break",
			"label": "FBR Status", "insert_after": insert_after, "collapsible": 1},
		{"fieldname": "pk_sales_tax_registration_type", "fieldtype": "Select",
			"options": "\nRegistered\nUnregistered", "label": "Sales Tax Registration Type",
			"insert_after": "pk_fbr_status_section"},
		{"fieldname": "pk_sales_tax_atl_status", "fieldtype": "Select",
			"options": "\nActive\nIn-Active", "label": "Sales Tax ATL Status",
			"insert_after": "pk_sales_tax_registration_type"},
		{"fieldname": "pk_fbr_col_break", "fieldtype": "Column Break",
			"insert_after": "pk_sales_tax_atl_status"},
		{"fieldname": "pk_income_tax_filer_status", "fieldtype": "Select",
			"options": "\nFiler\nNon-Filer", "label": "Income Tax Filer Status",
			"description": "From income-tax ATL — used for WHT rates only",
			"insert_after": "pk_fbr_col_break"},
		{"fieldname": "pk_statl_last_verified", "fieldtype": "Datetime",
			"label": "STATL Last Verified", "read_only": 1,
			"insert_after": "pk_income_tax_filer_status"},
		{"fieldname": "pk_fbr_province", "fieldtype": "Link", "options": "FBR Province",
			"label": "FBR Province", "insert_after": "pk_statl_last_verified"},
		{"fieldname": "pk_fbr_address", "fieldtype": "Data", "label": "FBR Address",
			"insert_after": "pk_fbr_province"},
		{"fieldname": "pk_associated_tax_parties", "fieldtype": "Table",
			"options": "Associated Tax Party", "label": "Associated Tax Parties",
			"insert_after": "pk_fbr_address"},
	]


def _invoice_header_fields(is_sales):
	fields = [
		{"fieldname": "pk_fbr_section", "fieldtype": "Section Break", "label": "FBR",
			"insert_after": "due_date" if is_sales else "bill_date", "collapsible": 1},
		{"fieldname": "pk_is_tax_invoice", "fieldtype": "Check",
			"label": "Sales Tax Invoice (report to FBR)", "default": "1",
			"insert_after": "pk_fbr_section", "allow_on_submit": 0},
		{"fieldname": "pk_tax_party", "fieldtype": "Link", "options": "Tax Party",
			"label": "Tax Party (third-party tax identity)",
			"description": "Leave empty when the tax document names the commercial party itself",
			"insert_after": "pk_is_tax_invoice"},
	]
	if is_sales:
		fields += [
			{"fieldname": "pk_fbr_col1", "fieldtype": "Column Break",
				"insert_after": "pk_tax_party"},
			{"fieldname": "pk_fbr_invoice_number", "fieldtype": "Data",
				"label": "FBR Invoice Number", "read_only": 1, "no_copy": 1,
				"insert_after": "pk_fbr_col1"},
			{"fieldname": "pk_fbr_posting_status", "fieldtype": "Select",
				"options": "\nPending\nPosted\nFailed", "label": "FBR Posting Status",
				"read_only": 1, "no_copy": 1, "insert_after": "pk_fbr_invoice_number"},
			{"fieldname": "pk_fbr_posting_date", "fieldtype": "Datetime",
				"label": "FBR Posting Date", "read_only": 1, "no_copy": 1,
				"insert_after": "pk_fbr_posting_status"},
			{"fieldname": "pk_buyer_reg_type_snapshot", "fieldtype": "Data",
				"label": "Buyer Registration Type (snapshot)", "read_only": 1,
				"no_copy": 1, "insert_after": "pk_fbr_posting_date"},
			{"fieldname": "pk_buyer_atl_snapshot", "fieldtype": "Data",
				"label": "Buyer ATL Status (snapshot)", "read_only": 1, "no_copy": 1,
				"insert_after": "pk_buyer_reg_type_snapshot"},
			{"fieldname": "pk_pra_invoice_number", "fieldtype": "Data",
				"label": "PRA Invoice Number", "read_only": 1, "no_copy": 1,
				"insert_after": "pk_buyer_atl_snapshot"},
			{"fieldname": "pk_pra_posting_status", "fieldtype": "Select",
				"options": "\nPending\nPosted", "label": "PRA Posting Status",
				"read_only": 1, "no_copy": 1, "insert_after": "pk_pra_invoice_number"},
		]
	else:
		fields += [
			{"fieldname": "pk_fbr_col1", "fieldtype": "Column Break",
				"insert_after": "pk_tax_party"},
			{"fieldname": "pk_supplier_fbr_invoice_no", "fieldtype": "Data",
				"label": "Supplier FBR Invoice No",
				"description": "The supplier's FBR invoice number — used for Annex-A matching",
				"insert_after": "pk_fbr_col1"},
		]
	return fields


CUSTOM_FIELDS["Sales Invoice Item"] = _line_tax_fields() + _row_fbr_fields()
CUSTOM_FIELDS["Purchase Invoice Item"] = _line_tax_fields() + _row_fbr_fields()
CUSTOM_FIELDS["Sales Invoice"] = _invoice_header_fields(True)
CUSTOM_FIELDS["Purchase Invoice"] = _invoice_header_fields(False)
CUSTOM_FIELDS["Customer"] = _party_status_fields("tax_id")
CUSTOM_FIELDS["Supplier"] = _party_status_fields("tax_id")
CUSTOM_FIELDS["Item"] = [
	{"fieldname": "pk_fbr_section", "fieldtype": "Section Break", "label": "FBR",
		"insert_after": "customs_tariff_number", "collapsible": 1},
	{"fieldname": "pk_fbr_transaction_type", "fieldtype": "Link",
		"options": "FBR Transaction Type", "label": "FBR Transaction Type",
		"insert_after": "pk_fbr_section"},
	{"fieldname": "pk_retail_price", "fieldtype": "Currency",
		"label": "Retail Price (3rd Schedule)", "insert_after": "pk_fbr_transaction_type"},
	{"fieldname": "pk_fixed_notified_value", "fieldtype": "Currency",
		"label": "Fixed Notified Value", "insert_after": "pk_retail_price"},
	{"fieldname": "pk_sro_schedule", "fieldtype": "Link", "options": "FBR SRO",
		"label": "Default SRO Schedule", "insert_after": "pk_fixed_notified_value"},
	{"fieldname": "pk_sro_item_serial", "fieldtype": "Data",
		"label": "Default SRO Item Serial", "insert_after": "pk_sro_schedule"},
]
CUSTOM_FIELDS["Payment Entry"] = [
	{"fieldname": "pk_payer", "fieldtype": "Link", "options": "Tax Party",
		"label": "Actual Payer/Remitter (if third party)",
		"insert_after": "party_name"},
	{"fieldname": "pk_apply_wht", "fieldtype": "Check", "label": "Apply WHT",
		"insert_after": "pk_payer"},
]
CUSTOM_FIELDS["Payment Entry Reference"] = [
	{"fieldname": "pk_wht_section", "fieldtype": "Link", "options": "WHT Section",
		"label": "WHT Section", "insert_after": "allocated_amount"},
	{"fieldname": "pk_wht_rate", "fieldtype": "Float", "label": "WHT Rate (%)",
		"insert_after": "pk_wht_section"},
	{"fieldname": "pk_wht_amount", "fieldtype": "Currency", "label": "WHT Amount",
		"insert_after": "pk_wht_rate"},
]

for _df_list in CUSTOM_FIELDS.values():
	for _df in _df_list:
		_df.setdefault("module", MODULE)


def after_install():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


def after_migrate():
	# Idempotent — keeps fields present on every migrate
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
