# Copyright (c) 2026, SpotLedger
"""Fixed/per-unit tax component (3rd Schedule per-unit value, or the
Rs/unit part of a genuine Fixed or Compound-rate SRO entry) — posts onto
the SAME Input/Output Sales Tax account as the percentage component,
never a dedicated "Fixed" account.

There's only one Input ST account and one Output ST account, full stop:
the GL doesn't need to know how a number was computed, only how much and
which direction. What computed it — 18%, Rs.60/kg, or both together for a
compound-rate item like Potassium Chlorate — is recorded on the invoice
line via item_tax_template + Item Tax Template.pk_fixed_per_unit_rate, not
by which account it hit.

Mechanics: this can't be a second Item Tax Template row on the main
account (Item Tax Template rejects two rows on one account outright:
"entered twice in Item Tax"), and it can't be a per-item item_tax_rate
override either (same account, same collision, one slot). So — same
technique as supplier_tax_reconciliation.py's rounding correction — it
lands as a staged Actual amount, item-wise breakup authored by hand,
dont_recompute_tax set so reset_item_wise_tax_details() (taxes_and_totals.py)
preserves it verbatim instead of recomputing it. Runs in before_validate,
before the controller's own first calculate_taxes_and_totals() call, so it
takes effect in the same pass — no second recompute needed."""

import frappe
from frappe.utils import flt

PK_TAX_CATEGORY = "Sales Tax Fixed"  # amount-only category (line_taxes.py) —
# folds into pk_st_amount, never sets the displayed pk_st_rate


def apply_fixed_components(doc, method=None):
	"""Purchase/Sales Invoice before_validate hook — runs after
	resolve_templates so item.item_tax_template is already resolved."""
	if not doc.get("pk_is_tax_invoice") or not doc.get("items"):
		return

	is_sales = doc.doctype == "Sales Invoice"
	account = frappe.db.get_value("FBR Settings", {"company": doc.company},
		"account_sales_tax" if is_sales else "account_input_sales_tax")
	if not account:
		return

	entries = []  # (item, amount)
	for item in doc.items:
		tmpl = item.get("item_tax_template")
		if not tmpl:
			continue
		per_unit = flt(frappe.get_cached_value(
			"Item Tax Template", tmpl, "pk_fixed_per_unit_rate"))
		if not per_unit:
			continue
		amount = flt(per_unit * flt(item.qty), item.precision("amount") or 2)
		if amount:
			entries.append((item, amount))

	if not entries:
		return

	tax_row = _get_fixed_component_row(doc, account)
	total = flt(sum(amount for _item, amount in entries), tax_row.precision("tax_amount"))
	tax_row.tax_amount = total
	tax_row.dont_recompute_tax = 1

	item_entries = doc.get("_item_wise_tax_details")
	if item_entries is None:
		item_entries = []
		doc._item_wise_tax_details = item_entries
	for item, amount in entries:
		item_entries.append(frappe._dict(
			item=item, tax=tax_row, rate=0, amount=amount, taxable_amount=0))


def _get_fixed_component_row(doc, account):
	for row in doc.get("taxes", []):
		if row.account_head == account and row.get("pk_tax_category") == PK_TAX_CATEGORY:
			return row
	base_row = next((r for r in doc.get("taxes", []) if r.account_head == account), None)
	return doc.append("taxes", {
		"charge_type": "Actual",
		"account_head": account,
		"cost_center": base_row.get("cost_center") if base_row else None,
		"category": (base_row.get("category") if base_row else None) or "Total",
		"tax_amount": 0,
		"dont_recompute_tax": 1,
		"description": "Sales Tax (Fixed/Qty)",
		"add_deduct_tax": "Add",
		"pk_tax_category": PK_TAX_CATEGORY,
	})
