# Copyright (c) 2026, SpotLedger
"""Withholding tax on Payment Entry — via the NATIVE Advance Taxes and Charges
table (add_deduct_tax = Deduct). No build_gl_map override: the engine's own
GL handling stays intact.

Core design point: WHT is a PER-INVOICE decision, not a per-payment one. One
payment may settle five invoices, each under a different section or a
different rate scenario within the same section (e.g. s.153(1)(a) has
distinct rates for goods vs. company vs. non-company). So the user picks a
WHT Rate — not just a WHT Section — on each Payment Entry Reference row; the
header Advance Taxes and Charges rows are only the GL-account-level rollup
of those per-invoice decisions, grouped by section.

Runs in before_validate so the appended rows are included in the engine's own
totals calculation. Rows this module manages are tagged via pk-prefixed
description; other manually added tax rows are never touched."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

WHT_TAG = "WHT:"


def _rate_for(wht_rate, filer_status):
	if wht_rate.not_a_flat_rate:
		frappe.throw(_(
			"WHT Rate {0} ({1}) is not a flat-rate scenario and has no "
			"percentage configured — set the rate manually before use."
		).format(wht_rate.name, wht_rate.condition))
	return flt(wht_rate.filer_rate) if filer_status == "Filer" else flt(
		wht_rate.non_filer_rate)


def _validate_dated_coverage(wht_rate, posting_date):
	if wht_rate.valid_from and getdate(wht_rate.valid_from) > getdate(posting_date):
		frappe.throw(_(
			"WHT Rate {0} is not valid until {1}").format(
			wht_rate.name, wht_rate.valid_from))
	if wht_rate.valid_upto and getdate(wht_rate.valid_upto) < getdate(posting_date):
		frappe.throw(_(
			"WHT Rate {0} expired on {1} — pick the current rate for this "
			"section/condition").format(wht_rate.name, wht_rate.valid_upto))


def calculate_wht(doc, method=None):
	if doc.doctype != "Payment Entry":
		return

	# drop rows we previously generated (keep any the user added by hand)
	doc.taxes = [t for t in (doc.get("taxes") or [])
		if not (t.description or "").startswith(WHT_TAG)]

	if not doc.get("pk_apply_wht"):
		return
	if doc.get("party_type") not in ("Supplier", "Customer"):
		return

	filer_status = frappe.db.get_value(doc.party_type, doc.party,
		"pk_income_tax_filer_status") or "Non-Filer"

	sections = {}
	summary = {}  # section_name -> total amount
	for ref in doc.get("references", []):
		rate_name = ref.get("pk_wht_rate")
		if not rate_name:
			continue

		wht_rate = frappe.get_cached_doc("WHT Rate", rate_name)
		_validate_dated_coverage(wht_rate, doc.posting_date)
		section_name = wht_rate.section
		if section_name not in sections:
			sections[section_name] = frappe.get_doc("WHT Section", section_name)
		section = sections[section_name]

		rate = _rate_for(wht_rate, filer_status)
		amount = flt(flt(ref.allocated_amount) * rate / 100.0, 2)

		ref.pk_wht_section = section_name
		ref.pk_wht_computed_rate = rate
		ref.pk_wht_amount = amount

		summary[section_name] = summary.get(section_name, 0) + amount

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
