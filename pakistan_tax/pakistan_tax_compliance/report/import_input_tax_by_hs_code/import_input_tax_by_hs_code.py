# Copyright (c) 2026, SpotLedger
"""Import Input Tax by HS Code — line-level detail behind the aggregate
"Input ST"/"WHT Receivable" rows Tax Ledger Entry posts per Landed Cost
Voucher (see pakistan_tax.tax_ledger.import_posting.on_lcv_submit).

Same pattern as Annex-C: HS-code granularity is answered by joining the
source document's item rows to Item.customs_tariff_number at report time,
not by carrying hs_code on Tax Ledger Entry itself.

Depends on custom fields owned by whatever import-management app is
installed (importmanager, as of this writing) on Landed Cost Voucher /
Landed Cost Item — not on pakistan_tax. If those columns don't exist (no
such app installed), this returns an explanatory empty result instead of a
raw SQL error.
"""

import frappe

REQUIRED_COLUMNS = [
	("Landed Cost Voucher", "custom_landed_cost_voucher_type"),
	("Landed Cost Voucher", "custom_import_document"),
	("Landed Cost Item", "custom_stamnt"),
	("Landed Cost Item", "custom_ast"),
	("Landed Cost Item", "custom_it"),
]


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": "LCV", "fieldname": "lcv", "fieldtype": "Link",
			"options": "Landed Cost Voucher", "width": 150},
		{"label": "GD No", "fieldname": "gd_no", "width": 120},
		{"label": "Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": "Item", "fieldname": "item_code", "fieldtype": "Link",
			"options": "Item", "width": 140},
		{"label": "HS Code", "fieldname": "hs_code", "width": 95},
		{"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "width": 70},
		{"label": "Sales Tax", "fieldname": "st", "fieldtype": "Currency", "width": 100},
		{"label": "Additional ST", "fieldname": "ast", "fieldtype": "Currency", "width": 100},
		{"label": "Advance Income Tax", "fieldname": "it", "fieldtype": "Currency", "width": 130},
	]

	for dt, col in REQUIRED_COLUMNS:
		if not frappe.db.has_column(dt, col):
			frappe.msgprint(
				"This report needs an import-management app (e.g. importmanager) "
				"installed — {0}.{1} doesn't exist on this site.".format(dt, col)
			)
			return columns, []

	conditions = ("lcv.docstatus = 1 and lcv.custom_landed_cost_voucher_type = 'Import'")
	values = {}
	if filters.get("company"):
		conditions += " and lcv.company = %(company)s"
		values["company"] = filters["company"]
	if filters.get("from_date"):
		conditions += " and lcv.posting_date >= %(from_date)s"
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions += " and lcv.posting_date <= %(to_date)s"
		values["to_date"] = filters["to_date"]

	data = frappe.db.sql(f"""
		select lcv.name as lcv, imp.gd_no as gd_no, lcv.posting_date,
			lci.item_code, item.customs_tariff_number as hs_code,
			lci.qty,
			lci.custom_stamnt as st, lci.custom_ast as ast, lci.custom_it as it
		from `tabLanded Cost Voucher` lcv
		join `tabLanded Cost Item` lci on lci.parent = lcv.name
		left join `tabItem` item on item.name = lci.item_code
		left join `tabImportDoc` imp on imp.name = lcv.custom_import_document
		where {conditions}
		order by lcv.posting_date, lcv.name, lci.idx
	""", values, as_dict=True)

	return columns, data
