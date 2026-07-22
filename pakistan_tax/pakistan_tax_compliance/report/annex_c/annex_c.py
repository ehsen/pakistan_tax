# Copyright (c) 2026, SpotLedger
"""Annex-C (domestic sales) — generated from exactly the FBR-reported set:
submitted Sales Invoices with pk_is_tax_invoice = 1, reading frozen snapshots."""

import frappe


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": "Invoice", "fieldname": "invoice", "fieldtype": "Link",
			"options": "Sales Invoice", "width": 140},
		{"label": "FBR Invoice No", "fieldname": "fbr_invoice_no", "width": 170},
		{"label": "Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": "Buyer", "fieldname": "buyer", "width": 160},
		{"label": "Buyer NTN/CNIC", "fieldname": "buyer_ntn", "width": 120},
		{"label": "Reg. Type", "fieldname": "reg_type", "width": 95},
		{"label": "HS Code", "fieldname": "hs_code", "width": 95},
		{"label": "Sale Type", "fieldname": "sale_type", "width": 170},
		{"label": "Rate", "fieldname": "rate_desc", "width": 90},
		{"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "width": 70},
		{"label": "UOM", "fieldname": "uom", "width": 80},
		{"label": "Value Excl. ST", "fieldname": "value_excl",
			"fieldtype": "Currency", "width": 110},
		{"label": "Sales Tax", "fieldname": "st", "fieldtype": "Currency", "width": 100},
		{"label": "Further Tax", "fieldname": "ft", "fieldtype": "Currency", "width": 100},
	]

	conditions = "si.docstatus = 1 and si.pk_is_tax_invoice = 1"
	values = {}
	if filters.get("company"):
		conditions += " and si.company = %(company)s"
		values["company"] = filters["company"]
	if filters.get("from_date"):
		conditions += " and si.posting_date >= %(from_date)s"
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		conditions += " and si.posting_date <= %(to_date)s"
		values["to_date"] = filters["to_date"]

	data = frappe.db.sql(f"""
		select si.name as invoice, si.pk_fbr_invoice_number as fbr_invoice_no,
			si.posting_date,
			coalesce(tp.party_name, si.customer_name) as buyer,
			coalesce(tp.ntn_cnic, c.tax_id) as buyer_ntn,
			si.pk_buyer_reg_type_snapshot as reg_type,
			item.customs_tariff_number as hs_code,
			sii.pk_fbr_transaction_type as sale_type,
			sii.pk_fbr_rate_desc as rate_desc,
			abs(sii.stock_qty) as qty, sii.stock_uom as uom,
			abs(sii.net_amount) as value_excl,
			abs(sii.pk_st_amount) as st,
			abs(sii.pk_further_tax_amount) as ft
		from `tabSales Invoice` si
		join `tabSales Invoice Item` sii on sii.parent = si.name
		left join `tabItem` item on item.name = sii.item_code
		left join `tabCustomer` c on c.name = si.customer
		left join `tabTax Party` tp on tp.name = si.pk_tax_party
		where {conditions}
		order by si.posting_date, si.name, sii.idx
	""", values, as_dict=True)

	return columns, data
