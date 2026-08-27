# Copyright (c) 2026, SpotLedger
"""Populate per-row Pakistan tax fields from the native engine's item-wise
breakup (plan §3.1: line-item fields are OUTPUTS of the engine, never inputs).

Source of truth: the temp `_item_wise_tax_details` list the engine builds
during calculate_taxes_and_totals (persisted as the `Item Wise Tax Detail`
child table on save in v16). Amounts there are in company currency; we store
document-currency values on the rows to match rate/amount columns.
"""

import frappe
from frappe import _
from frappe.utils import flt

# pk_tax_category -> which row fields it feeds. "Fixed"/"Rounding Adjustment"
# variants are per-unit (On Item Quantity) rows that must fold into the
# amount but never override the displayed percentage rate.
ST_CATEGORIES = ("Sales Tax", "Sales Tax Fixed", "Sales Tax Rounding Adjustment")
FT_CATEGORY = "Further Sales Tax"
AT_CATEGORIES = ("Advance Tax 236G", "Advance Tax 236G Rounding Adjustment")


def _iter_item_wise_details(doc):
	"""Yield (item_row_name, pk_tax_category, rate, doc_currency_amount)."""
	conversion = flt(doc.get("conversion_rate")) or 1

	details = doc.get("_item_wise_tax_details")
	if details:
		for row in details:
			category = row.tax.get("pk_tax_category")
			if not category:
				continue
			yield row.item.name, category, flt(row.rate), flt(row.amount) / conversion
		return

	# Fallback: persisted child table (doc loaded from DB without recalculation)
	tax_categories = {t.name: t.get("pk_tax_category") for t in doc.get("taxes", [])}
	for row in doc.get("item_wise_tax_details", []):
		category = tax_categories.get(row.tax_row)
		if not category:
			continue
		yield row.item_row, category, flt(row.rate), flt(row.amount) / conversion


def _resolve_and_enforce_tax_authority(doc):
	"""One invoice, one tax authority (plan §3.10) — resolved from the
	items' Item Tax Templates, never inferred/split. Both this app's actual
	integration payload builders (FBR Digital Invoicing, PRA POS) serialize
	every item on the document into a single outbound call, so a document
	mixing authorities can never be filed correctly — reject it here, at
	validate, rather than let it reach submit or a downstream report."""
	authorities = {row.pk_tax_authority for row in doc.get("items", [])
		if row.get("pk_tax_authority")}
	if len(authorities) > 1:
		frappe.throw(_(
			"This invoice mixes items taxed by different authorities ({0}). "
			"Each authority's Digital Invoicing/POS integration expects one "
			"complete, self-contained invoice — split these into separate "
			"invoices, one per authority, before submitting."
		).format(", ".join(sorted(authorities))))
	if authorities:
		doc.pk_tax_authority = authorities.pop()


def update_line_tax_fields(doc, method=None):
	"""doc_events.validate on Sales Invoice / Purchase Invoice — runs after the
	controller's own validate (which includes calculate_taxes_and_totals)."""
	_resolve_and_enforce_tax_authority(doc)

	totals = {}  # item_row_name -> dict
	for item_row, category, rate, amount in _iter_item_wise_details(doc):
		agg = totals.setdefault(item_row, {
			"st_rate": 0, "st_amount": 0, "ft_rate": 0, "ft_amount": 0,
			"at_rate": 0, "at_amount": 0})
		if category in ST_CATEGORIES:
			agg["st_amount"] += amount
			if category == "Sales Tax":
				agg["st_rate"] = rate
		elif category == FT_CATEGORY:
			agg["ft_amount"] += amount
			agg["ft_rate"] = rate
		elif category in AT_CATEGORIES:
			agg["at_amount"] += amount
			if category == "Advance Tax 236G":
				agg["at_rate"] = rate

	for item in doc.get("items", []):
		agg = totals.get(item.name) or {}
		precision = item.precision("pk_st_amount") or 2
		item.pk_st_rate = flt(agg.get("st_rate", 0))
		item.pk_st_amount = flt(agg.get("st_amount", 0), precision)
		item.pk_further_tax_rate = flt(agg.get("ft_rate", 0))
		item.pk_further_tax_amount = flt(agg.get("ft_amount", 0), precision)
		item.pk_advance_tax_rate = flt(agg.get("at_rate", 0))
		item.pk_advance_tax_amount = flt(agg.get("at_amount", 0), precision)
		item.pk_total_incl_tax = flt(
			flt(item.net_amount) + item.pk_st_amount + item.pk_further_tax_amount,
			precision)
