# Copyright (c) 2026, SpotLedger
"""3rd Schedule Goods (plan §3.3): ST = retail/notified price x rate% x qty.

Modeled as a per-unit tax: each 3rd Schedule item gets its OWN generated
template carrying retail_price x rate% per unit as pk_fixed_per_unit_rate —
no Item Tax Template row (there's nowhere for one: it would have to share
the Input/Output Sales Tax account with any percentage-rate row, and Item
Tax Template rejects two rows on one account outright). At invoice time
transactions/fixed_component.py reads that field and stages the amount
directly onto the Input/Output Sales Tax account — same account as every
other Sales Tax line, only the template on the row records that this one
was computed from retail price rather than a plain rate.

This is the one deliberate exception to template immutability: the item's
template is regenerated when its retail price changes (derived data, history
lives in the Item timeline)."""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

THIRD_SCHEDULE_TT = "3rd Schedule Goods"


def _default_rate(company):
	"""The default (is_default) open association's rate for 3rd Schedule."""
	assoc = frappe.get_all("FBR Transaction Type Rate",
		filters={"transaction_type": THIRD_SCHEDULE_TT,
			"valid_upto": ("is", "not set"), "is_default": 1},
		fields=["fbr_rate"], limit=1)
	if not assoc:
		assoc = frappe.get_all("FBR Transaction Type Rate",
			filters={"transaction_type": THIRD_SCHEDULE_TT,
				"valid_upto": ("is", "not set")},
			fields=["fbr_rate"], limit=1)
	if not assoc:
		frappe.throw(_(
			"No open rate association for '3rd Schedule Goods' — run the FBR sync"))
	return frappe.get_doc("FBR Rate", assoc[0].fbr_rate)


def sync_third_schedule_template(doc, method=None):
	"""Item validate hook."""
	if doc.get("pk_fbr_transaction_type") != THIRD_SCHEDULE_TT:
		return

	base = max(flt(doc.get("pk_fixed_notified_value")), flt(doc.get("pk_retail_price")))
	if base <= 0:
		frappe.throw(_(
			"3rd Schedule item {0} requires a Retail Price or Fixed Notified "
			"Value — ST is computed on it.").format(doc.item_code or doc.name))

	for settings in frappe.get_all("FBR Settings", filters={"is_enabled": 1},
			fields=["name", "company", "account_sales_tax", "account_input_sales_tax"]):
		if not settings.account_sales_tax or not settings.account_input_sales_tax:
			continue
		rate = _default_rate(settings.company)
		per_unit = flt(base * flt(rate.percent_component) / 100.0, 4)
		title = f"3SCH {doc.item_code or doc.name}"
		existing = frappe.db.get_value("Item Tax Template",
			{"company": settings.company, "title": title})

		# rate-0 rows on the Sales Tax account: Item Tax Template.taxes is
		# itself mandatory, and 3rd Schedule items have no percentage
		# component of their own — the real amount is pk_fixed_per_unit_rate,
		# staged at invoice time (transactions/fixed_component.py)
		placeholder_rows = [
			{"tax_type": account, "tax_rate": 0, "pk_tax_category": "Sales Tax"}
			for account in (settings.account_sales_tax, settings.account_input_sales_tax)
		]

		if existing:
			tmpl = frappe.get_doc("Item Tax Template", existing)
			tmpl.pk_fixed_per_unit_rate = per_unit
			tmpl.pk_fbr_transaction_type = THIRD_SCHEDULE_TT
			tmpl.pk_fbr_rate = rate.name
			if not tmpl.taxes:
				tmpl.taxes = placeholder_rows
			tmpl.flags.ignore_permissions = True
			tmpl.save()
			template_name = tmpl.name
		else:
			tmpl = frappe.get_doc({
				"doctype": "Item Tax Template",
				"title": title,
				"company": settings.company,
				"pk_fbr_transaction_type": THIRD_SCHEDULE_TT,
				"pk_fbr_rate": rate.name,
				"pk_is_fbr_generated": 1,
				"pk_fixed_per_unit_rate": per_unit,
				"taxes": placeholder_rows,
			})
			tmpl.insert(ignore_permissions=True)
			template_name = tmpl.name

		# expose via the item's native dated tax rows so resolution picks it up
		if not any(r.item_tax_template == template_name for r in doc.get("taxes", [])):
			doc.append("taxes", {"item_tax_template": template_name,
				"valid_from": nowdate()})
