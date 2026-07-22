# Copyright (c) 2026, SpotLedger
"""Withholding tax on Payment Entry — via the NATIVE Advance Taxes and Charges
table (add_deduct_tax = Deduct). No build_gl_map override: the engine's own
GL handling stays intact (the old app's override is retired).

Runs in before_validate so the appended rows are included in the engine's own
totals calculation. Rows this module manages are tagged via pk-prefixed
description; other manually added tax rows are never touched."""

import frappe
from frappe import _
from frappe.utils import flt

WHT_TAG = "WHT:"


def _rate_for(section, filer_status):
	if filer_status == "Filer":
		return flt(section.filer_rate)
	return flt(section.non_filer_rate)


def calculate_wht(doc, method=None):
	if doc.doctype != "Payment Entry":
		return

	# drop rows we previously generated (keep user's own rows)
	doc.taxes = [t for t in (doc.get("taxes") or [])
		if not (t.description or "").startswith(WHT_TAG)]

	if not doc.get("pk_apply_wht"):
		return
	if doc.get("party_type") not in ("Supplier", "Customer"):
		return

	filer_status = frappe.db.get_value(doc.party_type, doc.party,
		"pk_income_tax_filer_status") or "Non-Filer"

	sections = {}
	summary = {}
	for ref in doc.get("references", []):
		section_name = ref.get("pk_wht_section")
		if not section_name:
			continue
		if section_name not in sections:
			sections[section_name] = frappe.get_doc("WHT Section", section_name)
		section = sections[section_name]

		rate = flt(ref.get("pk_wht_rate")) or _rate_for(section, filer_status)
		amount = flt(ref.allocated_amount) * rate / 100.0
		ref.pk_wht_rate = rate
		ref.pk_wht_amount = flt(amount, 2)
		summary[section_name] = summary.get(section_name, 0) + ref.pk_wht_amount

	for section_name, total in summary.items():
		if not total:
			continue
		section = sections[section_name]
		account = (section.payable_account if doc.payment_type == "Pay"
			else section.receivable_account)
		if not account:
			frappe.throw(_(
				"WHT Section {0} has no {1} account configured").format(
				section_name,
				"payable" if doc.payment_type == "Pay" else "receivable"))
		doc.append("taxes", {
			"charge_type": "Actual",
			"add_deduct_tax": "Deduct",
			"account_head": account,
			"description": f"{WHT_TAG} {section_name} ({filer_status})",
			"tax_amount": flt(total, 2),
		})
