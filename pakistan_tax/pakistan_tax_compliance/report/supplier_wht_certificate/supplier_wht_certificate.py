# Copyright (c) 2026, SpotLedger
"""u/s 164 certificate data: a supplier's withheld tax with CPR references.
Print this report as the certificate; also feeds the u/s 165 statement."""

import frappe


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": "Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": "Payment", "fieldname": "voucher_no", "fieldtype": "Link",
			"options": "Payment Entry", "width": 150},
		{"label": "Section", "fieldname": "section", "width": 100},
		{"label": "Taxable Amount", "fieldname": "taxable_amount",
			"fieldtype": "Currency", "width": 120},
		{"label": "Tax Withheld", "fieldname": "tax_amount",
			"fieldtype": "Currency", "width": 120},
		{"label": "Status", "fieldname": "status", "width": 100},
		{"label": "CPR No", "fieldname": "cpr_reference", "width": 170},
	]
	values = {}
	cond = "tax_type = 'WHT Payable' and is_reversal = 0"
	if filters.get("company"):
		cond += " and company = %(company)s"
		values["company"] = filters["company"]
	if filters.get("supplier"):
		cond += " and party = %(supplier)s"
		values["supplier"] = filters["supplier"]
	if filters.get("from_date"):
		cond += " and posting_date >= %(from_date)s"
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		cond += " and posting_date <= %(to_date)s"
		values["to_date"] = filters["to_date"]

	data = frappe.db.sql(f"""
		select posting_date, voucher_no, section, taxable_amount, tax_amount,
			status, cpr_reference
		from `tabTax Ledger Entry`
		where {cond}
		order by posting_date
	""", values, as_dict=True)
	return columns, data
