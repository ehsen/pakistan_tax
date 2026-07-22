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


CUSTOM_FIELDS["Sales Invoice Item"] = _line_tax_fields()
CUSTOM_FIELDS["Purchase Invoice Item"] = _line_tax_fields()


def after_install():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


def after_migrate():
	# Idempotent — keeps fields present on every migrate
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
