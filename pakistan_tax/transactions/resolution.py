# Copyright (c) 2026, SpotLedger
"""Template resolution (plan §3.5/§3.6) — runs in before_validate, i.e. BEFORE
the engine calculates, so resolved templates take effect in the same save.

Precedence (most specific wins — mirrors native selection):
1. row.item_tax_template already set (user/UI choice) — untouched
2. Item master dated tax rows (tax_category match beats blank, latest valid_from)
3. FBR Transaction Type dated default template

Documents with pk_is_tax_invoice = 0 are skipped entirely (§3.9)."""

import frappe
from frappe.utils import getdate


def _from_item_master(item_code, company, tax_category, posting_date):
	rows = frappe.get_all("Item Tax",
		filters={"parent": item_code, "parenttype": "Item"},
		fields=["item_tax_template", "tax_category", "valid_from"])
	best, best_key = None, None
	for row in rows:
		if row.tax_category and row.tax_category != (tax_category or ""):
			continue
		valid_from = getdate(row.valid_from) if row.valid_from else getdate("2000-01-01")
		if valid_from > getdate(posting_date):
			continue
		if frappe.db.get_value("Item Tax Template", row.item_tax_template,
				"company") != company:
			continue
		key = (1 if row.tax_category else 0, valid_from)
		if best_key is None or key > best_key:
			best, best_key = row.item_tax_template, key
	return best


def _from_transaction_type(tt_name, company, posting_date):
	if not tt_name:
		return None
	rows = frappe.get_all("FBR Transaction Type Template",
		filters={"parent": tt_name, "parenttype": "FBR Transaction Type"},
		fields=["item_tax_template", "valid_from"])
	best, best_from = None, None
	for row in rows:
		valid_from = getdate(row.valid_from)
		if valid_from > getdate(posting_date):
			continue
		if frappe.db.get_value("Item Tax Template", row.item_tax_template,
				"company") != company:
			continue
		if best_from is None or valid_from > best_from:
			best, best_from = row.item_tax_template, valid_from
	return best


def _apply_header_template(doc):
	"""Server-side fallback when the taxes table is empty (API-created docs)."""
	if doc.get("taxes"):
		return
	if doc.doctype == "Sales Invoice":
		category = doc.get("tax_category") or frappe.db.get_value(
			"Customer", doc.customer, "tax_category") or "Registered"
		title = f"Pakistan Sales - {category}" if category in (
			"Registered", "Unregistered") else "Pakistan Sales - Registered"
		template_dt = "Sales Taxes and Charges Template"
	else:
		title = "Pakistan Purchase"
		template_dt = "Purchase Taxes and Charges Template"

	name = frappe.db.get_value(template_dt, {"company": doc.company, "title": title})
	if not name:
		return
	template = frappe.get_doc(template_dt, name)
	doc.taxes_and_charges = name
	for row in template.taxes:
		doc.append("taxes", {
			"charge_type": row.charge_type,
			"account_head": row.account_head,
			"rate": row.rate,
			"description": row.description,
			"row_id": row.get("row_id"),
			"category": row.get("category"),
			"add_deduct_tax": row.get("add_deduct_tax"),
			"pk_tax_category": row.get("pk_tax_category"),
		})


def _effective_tax_category(doc):
	"""Document category, else the party's — server-side inserts often skip
	the UI path that copies it onto the document."""
	if doc.get("tax_category"):
		return doc.tax_category
	if doc.doctype == "Sales Invoice" and doc.get("customer"):
		return frappe.db.get_value("Customer", doc.customer, "tax_category")
	if doc.doctype == "Purchase Invoice" and doc.get("supplier"):
		return frappe.db.get_value("Supplier", doc.supplier, "tax_category")
	return None


def resolve_templates(doc, method=None):
	if not doc.get("pk_is_tax_invoice"):
		return

	_apply_header_template(doc)
	posting_date = doc.get("posting_date") or frappe.utils.nowdate()
	tax_category = _effective_tax_category(doc)

	for row in doc.get("items", []):
		if not row.get("item_code"):
			continue
		if not row.get("item_tax_template"):
			template = _from_item_master(row.item_code, doc.company,
				tax_category, posting_date)
			if not template:
				tt = row.get("pk_fbr_transaction_type") or frappe.db.get_value(
					"Item", row.item_code, "pk_fbr_transaction_type")
				row.pk_fbr_transaction_type = tt
				template = _from_transaction_type(tt, doc.company, posting_date)
			if template:
				row.item_tax_template = template

		# stamp SRO/serial from the applicability that produced this template
		if row.get("item_tax_template") and not row.get("pk_sro_schedule"):
			from pakistan_tax.pakistan_tax_compliance.doctype.sro_applicability\
				.sro_applicability import find_sro_for_row
			app = find_sro_for_row(row.item_code, doc.company, tax_category,
				posting_date, row.item_tax_template)
			if app:
				row.pk_sro_schedule = app.sro
				row.pk_sro_item_serial = app.sro_item_serial
