# Copyright (c) 2026, SpotLedger
"""Supplier Sales Tax Invoice reconciliation (Purchase Invoice Item).

The supplier's own tax invoice — not our engine's math — is what we actually
owe and what's admissible as input tax, so a booked line has to land on it
exactly, not sit next to it as a side note.

Rate is a hard gate, no tolerance: two SRO rates either match or they don't,
and a mismatch means the wrong tax category/SRO was applied somewhere — that
needs a human, never an auto-correction. Once the rate matches, any amount
gap can only be rounding on the same base x rate, and gets corrected into
the real invoice total, exactly on the item it belongs to.

Mechanics: item.item_tax_rate is rebuilt from item.item_tax_template on
every calculate_taxes_and_totals pass (BuyingController.update_item_tax_map),
and — for items whose Item master carries its own dated Item Tax rows —
validate_item_tax_template() actively reassigns item_tax_template back to
whatever the item master resolves to. Both make item_tax_template/
item_tax_rate a dead end for a one-off, per-invoice correction: it does not
survive a second recompute.

What does survive: a dedicated Actual-charge tax row with dont_recompute_tax
set, its item-wise breakup authored by hand into doc._item_wise_tax_details
before the second calculate_taxes_and_totals() call.
reset_item_wise_tax_details() (taxes_and_totals.py) preserves exactly those
entries for dont_recompute_tax rows instead of recomputing them, while the
row's own tax_amount is never reset for Actual charge type — it is read as
direct input, so the diff we set is exactly what lands in the grand total.
The correction posts to its own dedicated account (auto-created next to the
base account it corrects): item_tax_rate is a flat {account_head: rate} map,
so two rows sharing one account could not each carry a different override
anyway.
"""

import frappe
from frappe import _
from frappe.utils import flt

RATE_PRECISION = 2
FLOAT_EPSILON = 0.005  # float/rounding noise only — not a second tolerance

CHECKS = [
	{
		"label": _("Sales Tax"),
		"engine_rate": "pk_st_rate",
		"engine_amount": "pk_st_amount",
		"supplier_rate": "pk_supplier_st_rate",
		"supplier_amount": "pk_supplier_st_amount",
		"base_category": "Sales Tax",
		"adjustment_category": "Sales Tax Rounding Adjustment",
	},
	{
		"label": _("Advance Tax 236G"),
		"engine_rate": "pk_advance_tax_rate",
		"engine_amount": "pk_advance_tax_amount",
		"supplier_rate": "pk_supplier_advance_tax_rate",
		"supplier_amount": "pk_supplier_advance_tax_amount",
		"base_category": "Advance Tax 236G",
		"adjustment_category": "Advance Tax 236G Rounding Adjustment",
	},
]


def reconcile_supplier_tax(doc, method=None):
	"""Purchase Invoice validate hook — runs after update_line_tax_fields so
	pk_st_amount/pk_advance_tax_amount already hold this pass's engine
	output."""
	errors = []
	corrections = []  # (item, check, diff)

	for item in doc.get("items", []):
		for check in CHECKS:
			supplier_amount = item.get(check["supplier_amount"])
			supplier_rate = item.get(check["supplier_rate"])
			if not supplier_amount and not supplier_rate:
				continue  # no supplier figure entered for this tax on this line

			engine_rate = flt(item.get(check["engine_rate"]), RATE_PRECISION)
			supplier_rate_r = flt(supplier_rate, RATE_PRECISION)
			if engine_rate != supplier_rate_r:
				errors.append(_(
					"Row {0} ({1}): supplier rate {2}% does not match the "
					"applied rate {3}%.").format(
						item.idx, check["label"], supplier_rate_r, engine_rate))
				continue

			precision = item.precision(check["engine_amount"]) or 2
			diff = flt(flt(supplier_amount) - flt(item.get(check["engine_amount"])), precision)
			if abs(diff) <= FLOAT_EPSILON:
				continue
			corrections.append((item, check, diff))

	if errors:
		frappe.throw(_(
			"Supplier tax rate does not match the rate applied — this is a "
			"hard rule, not a rounding case:<br>{0}").format("<br>".join(errors)),
			title=_("Supplier Tax Rate Mismatch"))

	if not corrections:
		return

	row_totals = {}  # id(tax_row) -> {"row": tax_row, "total": float}
	for item, check, diff in corrections:
		tax_row = _get_adjustment_row(doc, check)
		bucket = row_totals.setdefault(id(tax_row), {"row": tax_row, "total": 0.0})
		bucket["total"] += diff
		_stage_item_wise_entry(doc, item, tax_row, diff)

	for bucket in row_totals.values():
		row = bucket["row"]
		row.tax_amount = flt(bucket["total"], row.precision("tax_amount"))
		row.dont_recompute_tax = 1

	doc.calculate_taxes_and_totals()
	from pakistan_tax.transactions.line_taxes import update_line_tax_fields
	update_line_tax_fields(doc)


def _find_base_row(doc, base_category):
	for row in doc.get("taxes", []):
		if row.get("pk_tax_category") == base_category:
			return row
	return None


def _get_adjustment_account(base_account_head):
	"""A dedicated account for the correction row, auto-created next to the
	base account. Not cosmetic: item_tax_rate is a flat {account_head: rate}
	map, so the base rate row and a correction row cannot share one account —
	whichever wrote the map entry last would win for both rows."""
	base = frappe.get_cached_doc("Account", base_account_head)
	name = f"{base.account_name} - Rounding Adjustment"
	existing = frappe.db.get_value("Account", {"company": base.company, "account_name": name})
	if existing:
		return existing
	acc = frappe.get_doc({
		"doctype": "Account",
		"account_name": name,
		"parent_account": base.parent_account,
		"company": base.company,
		"account_type": base.account_type,
		"is_group": 0,
	})
	acc.insert(ignore_permissions=True)
	return acc.name


def _get_adjustment_row(doc, check):
	base_row = _find_base_row(doc, check["base_category"])
	if not base_row:
		frappe.throw(_(
			"No {0} tax row found on this invoice to reconcile against"
		).format(check["label"]))

	adjustment_account = _get_adjustment_account(base_row.account_head)
	for row in doc.get("taxes", []):
		if row.account_head == adjustment_account:
			return row
	return doc.append("taxes", {
		"charge_type": "Actual",
		"account_head": adjustment_account,
		"cost_center": base_row.get("cost_center"),
		"category": base_row.get("category") or "Total",
		"tax_amount": 0,
		"dont_recompute_tax": 1,
		"description": check["adjustment_category"],
		"add_deduct_tax": "Add",
		"pk_tax_category": check["adjustment_category"],
	})


def _stage_item_wise_entry(doc, item, tax_row, diff):
	"""Author this row's item-wise breakup by hand — preserved verbatim by
	reset_item_wise_tax_details() on the next calculate_taxes_and_totals()
	pass because tax_row.dont_recompute_tax is set."""
	entries = doc.get("_item_wise_tax_details")
	if entries is None:
		entries = []
		doc._item_wise_tax_details = entries
	entries.append(frappe._dict(item=item, tax=tax_row, rate=0, amount=diff, taxable_amount=0))
