# Copyright (c) 2026, SpotLedger
"""u/s 164 certificate data: a supplier's withheld tax with CPR references,
against which invoice, and the exact rate scenario applied. Print this report
as the certificate; also feeds the u/s 165 statement."""

import frappe


def execute(filters=None):
	filters = filters or {}
	columns = [
		{"label": "Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": "Payment", "fieldname": "voucher_no", "fieldtype": "Link",
			"options": "Payment Entry", "width": 130},
		{"label": "Against Invoice", "fieldname": "against_voucher",
			"fieldtype": "Dynamic Link", "options": "against_voucher_type",
			"width": 130},
		{"label": "Section", "fieldname": "section", "fieldtype": "Link",
			"options": "WHT Section", "width": 100},
		{"label": "Applies When", "fieldname": "condition", "width": 150},
		{"label": "Rate (%)", "fieldname": "rate_applied", "fieldtype": "Float",
			"width": 80},
		{"label": "Taxable Amount", "fieldname": "taxable_amount",
			"fieldtype": "Currency", "width": 120},
		{"label": "Tax Withheld", "fieldname": "tax_amount",
			"fieldtype": "Currency", "width": 120},
		{"label": "Status", "fieldname": "status", "width": 100},
		{"label": "CPR No", "fieldname": "cpr_reference", "width": 170},
	]
	values = {}
	cond = "tle.tax_type = 'WHT Payable' and tle.is_reversal = 0"
	if filters.get("company"):
		cond += " and tle.company = %(company)s"
		values["company"] = filters["company"]
	if filters.get("supplier"):
		cond += " and tle.party = %(supplier)s"
		values["supplier"] = filters["supplier"]
	if filters.get("from_date"):
		cond += " and tle.posting_date >= %(from_date)s"
		values["from_date"] = filters["from_date"]
	if filters.get("to_date"):
		cond += " and tle.posting_date <= %(to_date)s"
		values["to_date"] = filters["to_date"]

	data = frappe.db.sql(f"""
		select tle.posting_date, tle.voucher_no, tle.against_voucher_type,
			tle.against_voucher, tle.section, wr.condition,
			(case when tle.taxable_amount != 0
				then round(tle.tax_amount / tle.taxable_amount * 100, 2)
				else 0 end) as rate_applied,
			tle.taxable_amount, tle.tax_amount, tle.status, tle.cpr_reference
		from `tabTax Ledger Entry` tle
		left join `tabWHT Rate` wr on wr.name = tle.wht_rate
		where {cond}
		order by tle.posting_date
	""", values, as_dict=True)
	return columns, data
