# Copyright (c) 2026, SpotLedger
"""Divergence Report (plan §3.9): the standing statement of the gap between
management reality and the FBR-filed view — unreported documents and
third-party-papered invoices, per commercial party."""

import frappe


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": "Type", "fieldname": "divergence_type", "width": 210},
		{"label": "Voucher", "fieldname": "voucher", "fieldtype": "Dynamic Link",
			"options": "voucher_type", "width": 150},
		{"label": "Voucher Type", "fieldname": "voucher_type", "width": 120},
		{"label": "Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": "Commercial Party", "fieldname": "party", "width": 170},
		{"label": "Tax Party (on paper)", "fieldname": "tax_party", "width": 170},
		{"label": "Net Total", "fieldname": "net_total", "fieldtype": "Currency",
			"width": 110},
		{"label": "Tax Involved", "fieldname": "tax_amount", "fieldtype": "Currency",
			"width": 110},
	]

	values = {}
	cond = "docstatus = 1"
	if filters.get("company"):
		cond += " and company = %(company)s"
		values["company"] = filters["company"]
	if filters.get("from_date"):
		cond += " and posting_date >= %(from_date)s"
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		cond += " and posting_date <= %(to_date)s"
		values["to_date"] = filters["to_date"]

	data = []
	for doctype, party_field in (("Sales Invoice", "customer"),
			("Purchase Invoice", "supplier")):
		rows = frappe.db.sql(f"""
			select name, posting_date, {party_field} as party, pk_tax_party,
				base_net_total, pk_is_tax_invoice
			from `tab{doctype}`
			where {cond} and (pk_is_tax_invoice = 0 or
				coalesce(pk_tax_party, '') != '')
			order by posting_date
		""", values, as_dict=True)
		for r in rows:
			if not r.pk_is_tax_invoice:
				dtype = "Unreported (not in tax view)"
			else:
				dtype = "Third-party tax identity"
			tax_amount = frappe.db.sql("""
				select coalesce(sum(pk_st_amount + pk_further_tax_amount), 0)
				from `tab{0} Item` where parent = %s""".format(doctype),
				r.name)[0][0]
			data.append({
				"divergence_type": dtype, "voucher": r.name,
				"voucher_type": doctype, "posting_date": r.posting_date,
				"party": r.party, "tax_party": r.pk_tax_party,
				"net_total": r.base_net_total, "tax_amount": tax_amount,
			})
	return columns, data
