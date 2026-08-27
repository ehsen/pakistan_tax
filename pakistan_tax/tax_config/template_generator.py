# Copyright (c) 2026, SpotLedger
"""Generators that turn synced FBR reference data into native ERPNext tax
configuration (plan §3.2, §3.3, §3.5).

- Item Tax Templates: one immutable template per (transaction type, rate,
  company). A rate change never edits a template — a new association generates
  a new template.
- Header templates: exactly two Sales Taxes and Charges Templates per company
  (Registered / Unregistered) plus purchase-side equivalents; buyer status
  picks between them via Tax Category + Tax Rule.
- FBR Transaction Type default templates: dated child rows mirroring the
  native Item Tax valid_from selection.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from pakistan_tax.tax_config.accounts import ensure_tax_accounts

FURTHER_TAX_RATE = 4.0  # s.3(1A) statutory rate; change here when law changes


def _template_title(tt_id, rate_id, rate_desc):
	title = f"FBR {tt_id}-{rate_id} {rate_desc}"
	return title[:120]


def _rate_rows(rate, settings):
	"""Template rows on the Input/Output Sales Tax account — every rate_type
	gets one (rate 0 for a pure Fixed rate, since Item Tax Template.taxes is
	itself mandatory and this is the only row a pure-Fixed template would
	otherwise have), so one template serves sales and purchase documents
	(the engine only matches accounts that appear in the document's header
	rows).

	The fixed/per-unit component (Fixed or Compound rate_type) is never a
	row here — it would have to share this same account with the percentage
	row above, and Item Tax Template rejects two rows on one account
	outright. It's carried on the template itself as pk_fixed_per_unit_rate
	(set by the caller) and staged at invoice time
	(transactions/fixed_component.py) onto that same account instead."""
	return [
		{"tax_type": account, "tax_rate": rate.percent_component or 0,
			"pk_tax_category": "Sales Tax"}
		for account in (settings.account_sales_tax, settings.account_input_sales_tax)
	]


def generate_item_tax_templates(company):
	"""Create missing Item Tax Templates for every unique (transaction type,
	rate) among open associations in the company's scoped provinces.

	Existing generated templates are never modified (immutability)."""
	settings = ensure_tax_accounts(company)

	province_scope = [p.province for p in (settings.provinces or [])] or None
	filters = {"valid_upto": ("is", "not set")}
	if province_scope:
		filters["province"] = ("in", province_scope)
	assocs = frappe.get_all("FBR Transaction Type Rate", filters=filters,
		fields=["transaction_type", "fbr_rate"])
	pairs = {(a.transaction_type, a.fbr_rate) for a in assocs}

	created, skipped = [], 0
	for tt_name, rate_name in sorted(pairs):
		tt_id = frappe.db.get_value("FBR Transaction Type", tt_name, "transaction_type_id")
		rate = frappe.get_doc("FBR Rate", rate_name)
		if rate.needs_review:
			continue  # human must decompose first (e.g. "DTRE")

		title = _template_title(tt_id, rate.rate_id, rate.rate_desc)
		existing = frappe.db.get_value("Item Tax Template",
			{"company": company, "pk_fbr_transaction_type": tt_name,
				"pk_fbr_rate": rate_name})
		if existing:
			skipped += 1
			continue

		taxes = _rate_rows(rate, settings)
		fixed_per_unit = flt(rate.fixed_component) if rate.rate_type in ("Fixed", "Compound") else 0
		if not taxes and not fixed_per_unit:
			continue

		doc = frappe.get_doc({
			"doctype": "Item Tax Template",
			"title": title,
			"company": company,
			"pk_fbr_transaction_type": tt_name,
			"pk_fbr_rate": rate_name,
			"pk_is_fbr_generated": 1,
			"pk_tax_authority": "FBR",
			"pk_fixed_per_unit_rate": fixed_per_unit,
			"taxes": taxes,
		})
		doc.insert(ignore_permissions=True)
		created.append(doc.name)

	return {"created": len(created), "existing": skipped, "names": created[:10]}


def update_transaction_type_defaults(company):
	"""Maintain the dated default-template child rows on FBR Transaction Type
	from is_default associations (valid_from mirrors the association)."""
	settings = frappe.get_doc("FBR Settings",
		frappe.db.get_value("FBR Settings", {"company": company}))
	province_scope = [p.province for p in (settings.provinces or [])] or None

	filters = {"valid_upto": ("is", "not set"), "is_default": 1}
	if province_scope:
		filters["province"] = ("in", province_scope)
	defaults = frappe.get_all("FBR Transaction Type Rate", filters=filters,
		fields=["transaction_type", "fbr_rate", "valid_from"])

	updated = 0
	for row in defaults:
		template = frappe.db.get_value("Item Tax Template",
			{"company": company, "pk_fbr_transaction_type": row.transaction_type,
				"pk_fbr_rate": row.fbr_rate})
		if not template:
			continue
		tt = frappe.get_doc("FBR Transaction Type", row.transaction_type)
		covered = any(d.item_tax_template == template
			and getdate(d.valid_from) <= getdate(row.valid_from)
			for d in tt.default_templates)
		if covered:
			continue
		tt.append("default_templates", {
			"valid_from": row.valid_from,
			"item_tax_template": template,
		})
		tt.save(ignore_permissions=True)
		updated += 1
	return {"default_rows_added": updated}


HEADER_TEMPLATES = {
	# (doctype, title suffix, include_further_tax)
	"sales": [
		("Sales Taxes and Charges Template", "Pakistan Sales - Registered", False),
		("Sales Taxes and Charges Template", "Pakistan Sales - Unregistered", True),
	],
	"purchase": [
		("Purchase Taxes and Charges Template", "Pakistan Purchase", False),
	],
}


def ensure_header_templates(company):
	"""Two sales header templates (Registered / Unregistered) + one purchase.

	ST carries rate 0 — real rates always come from the item's template via
	the engine's per-item override. No Sales Tax (Fixed/Qty) row here: the
	fixed/per-unit component isn't a static header row at all, it's staged
	dynamically per invoice (transactions/fixed_component.py) straight onto
	the same ST account above, only when an item on the invoice actually has
	one. Further Tax carries the statutory rate and only exists on the
	Unregistered template."""
	settings = ensure_tax_accounts(company)
	created = []

	def build_rows(is_sales, include_ft):
		st = settings.account_sales_tax if is_sales else settings.account_input_sales_tax
		rows = [
			{"charge_type": "On Net Total", "account_head": st, "rate": 0,
				"description": "Sales Tax", "pk_tax_category": "Sales Tax"},
		]
		if include_ft:
			rows.append({"charge_type": "On Net Total",
				"account_head": settings.account_further_tax,
				"rate": FURTHER_TAX_RATE, "description": "Further Tax (s.3(1A))",
				"pk_tax_category": "Further Sales Tax"})
		if not is_sales:
			for row in rows:
				row["category"] = "Total"
				row["add_deduct_tax"] = "Add"
		return rows

	for kind, templates in HEADER_TEMPLATES.items():
		is_sales = kind == "sales"
		for doctype, title, include_ft in templates:
			if frappe.db.get_value(doctype, {"company": company, "title": title}):
				continue
			doc = frappe.get_doc({
				"doctype": doctype,
				"title": title,
				"company": company,
				"taxes": build_rows(is_sales, include_ft),
			})
			doc.insert(ignore_permissions=True)
			created.append(doc.name)
	return {"created": created}


def ensure_tax_categories_and_rules(company):
	"""Tax Category Registered/Unregistered + Tax Rules selecting the header
	templates. Customer.tax_category is later maintained by the STATL chain."""
	created = []
	for category in ("Registered", "Unregistered"):
		if not frappe.db.exists("Tax Category", category):
			frappe.get_doc({"doctype": "Tax Category", "title": category}).insert(
				ignore_permissions=True)
			created.append(f"Tax Category: {category}")

	for category in ("Registered", "Unregistered"):
		template = frappe.db.get_value("Sales Taxes and Charges Template",
			{"company": company, "title": f"Pakistan Sales - {category}"})
		if not template:
			continue
		exists = frappe.db.exists("Tax Rule", {
			"company": company, "tax_type": "Sales", "tax_category": category})
		if exists:
			continue
		frappe.get_doc({
			"doctype": "Tax Rule",
			"tax_type": "Sales",
			"company": company,
			"tax_category": category,
			"sales_tax_template": template,
			"priority": 1,
			"use_for_shopping_cart": 0,
		}).insert(ignore_permissions=True)
		created.append(f"Tax Rule: Sales/{category}")
	return {"created": created}


def repair_generated_templates(company):
	"""Dev-phase schema fix: ensure every generated template carries both
	output and input account rows (older generations were output-only), and
	migrate the old per-account "Sales Tax Fixed" rows to
	pk_fixed_per_unit_rate — the fixed/per-unit component now stages onto
	the plain Input/Output Sales Tax account at invoice time instead of
	living on its own dedicated account/row."""
	settings = ensure_tax_accounts(company)
	fixed = 0
	for name in frappe.get_all("Item Tax Template",
			filters={"company": company, "pk_is_fbr_generated": 1}, pluck="name"):
		doc = frappe.get_doc("Item Tax Template", name)
		rate = frappe.get_doc("FBR Rate", doc.pk_fbr_rate)
		changed = False

		old_fixed_rows = [row for row in doc.taxes if row.get("pk_tax_category") == "Sales Tax Fixed"]
		if old_fixed_rows:
			doc.taxes = [row for row in doc.taxes if row not in old_fixed_rows]
			changed = True

		if rate.rate_type in ("Fixed", "Compound") and not doc.pk_fixed_per_unit_rate:
			doc.pk_fixed_per_unit_rate = flt(rate.fixed_component)
			changed = True

		have = {row.tax_type for row in doc.taxes}
		missing = [r for r in _rate_rows(rate, settings) if r["tax_type"] not in have]
		if missing:
			for row in missing:
				doc.append("taxes", row)
			changed = True

		if changed:
			doc.flags.ignore_permissions = True
			doc.save()
			fixed += 1
	return {"repaired": fixed}


@frappe.whitelist()
def setup_company_tax_config(company):
	"""One-shot Phase 3 bootstrap for a company."""
	frappe.only_for("System Manager")
	out = {}
	out["accounts"] = ensure_tax_accounts(company).name
	out["item_tax_templates"] = generate_item_tax_templates(company)
	out["defaults"] = update_transaction_type_defaults(company)
	out["header_templates"] = ensure_header_templates(company)
	out["tax_rules"] = ensure_tax_categories_and_rules(company)
	return out
