# Copyright (c) 2026, SpotLedger
"""Per-supplier input ST position: claimed vs FBR-declared (Annex-A matching
outcomes from the Tax Ledger)."""

import frappe


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": "Supplier", "fieldname": "party", "fieldtype": "Link",
			"options": "Supplier", "width": 180},
		{"label": "NTN", "fieldname": "party_ntn", "width": 110},
		{"label": "Claimed", "fieldname": "claimed", "fieldtype": "Currency", "width": 110},
		{"label": "Matched", "fieldname": "matched", "fieldtype": "Currency", "width": 110},
		{"label": "Mismatch", "fieldname": "mismatch", "fieldtype": "Currency", "width": 110},
		{"label": "Missing at FBR (at risk)", "fieldname": "missing",
			"fieldtype": "Currency", "width": 150},
		{"label": "Settled", "fieldname": "settled", "fieldtype": "Currency", "width": 110},
	]
	values = {}
	cond = "tax_type = 'Input ST' and is_reversal = 0"
	if filters.get("company"):
		cond += " and company = %(company)s"
		values["company"] = filters["company"]
	if filters.get("from_date"):
		cond += " and posting_date >= %(from_date)s"
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		cond += " and posting_date <= %(to_date)s"
		values["to_date"] = filters["to_date"]

	data = frappe.db.sql(f"""
		select party, party_ntn,
			sum(case when status = 'Claimed' then tax_amount else 0 end) as claimed,
			sum(case when status = 'Matched' then tax_amount else 0 end) as matched,
			sum(case when status = 'Mismatch' then tax_amount else 0 end) as mismatch,
			sum(case when status = 'Missing' then tax_amount else 0 end) as missing,
			sum(case when status = 'Settled' then tax_amount else 0 end) as settled
		from `tabTax Ledger Entry`
		where {cond}
		group by party, party_ntn
		order by missing desc, claimed desc
	""", values, as_dict=True)
	return columns, data
