# Copyright (c) 2026, SpotLedger
"""Tax Ledger Entry posting (plan §3.8) — the party-level tax subledger.

One immutable row per tax event; cancellation posts reversal rows, never
deletes. GL answers "how much"; TLE answers "which invoice, what state,
whose evidence"."""

import frappe
from frappe.utils import flt

from pakistan_tax.wht.payment_entry import WHT_TAG


def _insert(**kwargs):
	doc = frappe.get_doc({"doctype": "Tax Ledger Entry", **kwargs})
	doc.insert(ignore_permissions=True)
	return doc.name


def _party_ntn(doc):
	if doc.get("pk_tax_party"):
		return frappe.db.get_value("Tax Party", doc.pk_tax_party, "ntn_cnic")
	party_type = "Customer" if doc.doctype == "Sales Invoice" else "Supplier"
	party = doc.get("customer") if party_type == "Customer" else doc.get("supplier")
	return frappe.db.get_value(party_type, party, "tax_id")


def on_invoice_submit(doc, method=None):
	if not doc.get("pk_is_tax_invoice"):
		return
	is_sales = doc.doctype == "Sales Invoice"
	party_type = "Customer" if is_sales else "Supplier"
	party = doc.customer if is_sales else doc.supplier

	st = sum(flt(row.pk_st_amount) for row in doc.items)
	ft = sum(flt(row.pk_further_tax_amount) for row in doc.items)
	net = flt(doc.base_net_total)

	common = {
		"posting_date": doc.posting_date,
		"company": doc.company,
		"party_type": party_type,
		"party": party,
		"tax_party": doc.get("pk_tax_party"),
		"party_ntn": _party_ntn(doc),
		"voucher_type": doc.doctype,
		"voucher_no": doc.name,
		"fbr_invoice_no": (doc.get("pk_fbr_invoice_number") if is_sales
			else doc.get("pk_supplier_fbr_invoice_no")),
	}

	if is_sales:
		if st:
			_insert(tax_type="Output ST", status="Pending Return",
				taxable_amount=net, tax_amount=st, **common)
		if ft:
			_insert(tax_type="Further Tax", status="Pending Return",
				taxable_amount=net, tax_amount=ft, **common)
	else:
		if st:
			_insert(tax_type="Input ST", status="Claimed",
				taxable_amount=net, tax_amount=st, **common)


def on_payment_submit(doc, method=None):
	has_wht = any((t.description or "").startswith(WHT_TAG)
		for t in doc.get("taxes", []))
	if not has_wht:
		return
	for ref in doc.get("references", []):
		if not (ref.get("pk_wht_section") and flt(ref.get("pk_wht_amount"))):
			continue
		if doc.payment_type == "Pay":
			tax_type, status = "WHT Payable", "Withheld"
		else:
			tax_type, status = "WHT Receivable", "Awaiting CPR"
		_insert(
			posting_date=doc.posting_date,
			company=doc.company,
			party_type=doc.party_type,
			party=doc.party,
			tax_party=doc.get("pk_payer"),
			party_ntn=frappe.db.get_value(doc.party_type, doc.party, "tax_id"),
			section=ref.pk_wht_section,
			voucher_type="Payment Entry",
			voucher_no=doc.name,
			taxable_amount=flt(ref.allocated_amount),
			tax_amount=flt(ref.pk_wht_amount),
			tax_type=tax_type,
			status=status,
		)


def on_voucher_cancel(doc, method=None):
	"""Reversal rows for every TLE of the cancelled voucher."""
	for row in frappe.get_all("Tax Ledger Entry",
			filters={"voucher_type": doc.doctype, "voucher_no": doc.name,
				"is_reversal": 0},
			fields=["name", "posting_date", "company", "tax_type", "party_type",
				"party", "tax_party", "party_ntn", "section", "taxable_amount",
				"tax_amount", "fbr_invoice_no"]):
		_insert(
			posting_date=frappe.utils.nowdate(),
			company=row.company,
			tax_type=row.tax_type,
			party_type=row.party_type,
			party=row.party,
			tax_party=row.tax_party,
			party_ntn=row.party_ntn,
			section=row.section,
			voucher_type=doc.doctype,
			voucher_no=doc.name,
			taxable_amount=-flt(row.taxable_amount),
			tax_amount=-flt(row.tax_amount),
			fbr_invoice_no=row.fbr_invoice_no,
			status="Reversed",
			is_reversal=1,
			reversal_of=row.name,
		)
		frappe.db.set_value("Tax Ledger Entry", row.name, "status", "Reversed",
			update_modified=False)
