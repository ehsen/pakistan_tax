# Copyright (c) 2026, SpotLedger
"""Party-wise tax GL (plan §3.8, adopted from Ehsen's design).

Tax GL rows carry no party by default, so party-wise General Ledger on tax
accounts is impossible. Fix: rows whose tax account is flagged
`pk_track_party_wise` (on the Account, or per-row override) get the document's
party stamped onto their GL entries right after submit.

Implementation is a post-submit UPDATE (not an insert-path mutation): it can't
interfere with GL validation or row merging, and cancellation needs nothing
(v15+ marks is_cancelled instead of reposting).

Known gap: Repost Accounting Ledger recreates GL rows without the stamp —
re-run backfill_party_stamping() after reposts."""

import frappe


def _tracked_accounts(doc):
	tracked = set()
	for tax in doc.get("taxes", []):
		if not tax.get("account_head"):
			continue
		if tax.get("pk_track_party_wise"):
			tracked.add(tax.account_head)
		elif frappe.get_cached_value("Account", tax.account_head,
				"pk_track_party_wise"):
			tracked.add(tax.account_head)
	return tracked


def stamp_tax_gl_party(doc, method=None):
	"""on_submit (after the controller has posted GL)."""
	if doc.doctype == "Sales Invoice":
		party_type, party = "Customer", doc.customer
	elif doc.doctype == "Purchase Invoice":
		party_type, party = "Supplier", doc.supplier
	else:
		return

	tracked = _tracked_accounts(doc)
	if not tracked:
		return

	frappe.db.sql("""
		update `tabGL Entry`
		set party_type = %(party_type)s, party = %(party)s
		where voucher_type = %(voucher_type)s and voucher_no = %(voucher_no)s
			and account in %(accounts)s
			and coalesce(party, '') = ''
	""", {
		"party_type": party_type,
		"party": party,
		"voucher_type": doc.doctype,
		"voucher_no": doc.name,
		"accounts": tuple(tracked),
	})


def backfill_party_stamping(company=None):
	"""Stamp historical submitted invoices (and after Repost Accounting Ledger)."""
	stamped = 0
	for doctype in ("Sales Invoice", "Purchase Invoice"):
		filters = {"docstatus": 1}
		if company:
			filters["company"] = company
		for name in frappe.get_all(doctype, filters=filters, pluck="name"):
			doc = frappe.get_doc(doctype, name)
			stamp_tax_gl_party(doc)
			stamped += 1
	return stamped
