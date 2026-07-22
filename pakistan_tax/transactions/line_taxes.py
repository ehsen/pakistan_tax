# Copyright (c) 2026, SpotLedger
"""Populate per-row Pakistan tax fields from the native engine's item-wise
breakup (plan §3.1: line-item fields are OUTPUTS of the engine, never inputs).

Source of truth: the temp `_item_wise_tax_details` list the engine builds
during calculate_taxes_and_totals (persisted as the `Item Wise Tax Detail`
child table on save in v16). Amounts there are in company currency; we store
document-currency values on the rows to match rate/amount columns.
"""

import frappe
from frappe.utils import flt

# pk_tax_category -> which row fields it feeds
ST_CATEGORIES = ("Sales Tax", "Sales Tax Fixed")
FT_CATEGORY = "Further Sales Tax"
AT_CATEGORY = "Advance Tax 236G"


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


def update_line_tax_fields(doc, method=None):
	"""doc_events.validate on Sales Invoice / Purchase Invoice — runs after the
	controller's own validate (which includes calculate_taxes_and_totals)."""
	totals = {}  # item_row_name -> dict
	for item_row, category, rate, amount in _iter_item_wise_details(doc):
		agg = totals.setdefault(item_row, {
			"st_rate": 0, "st_amount": 0, "ft_rate": 0, "ft_amount": 0,
			"at_amount": 0})
		if category in ST_CATEGORIES:
			agg["st_amount"] += amount
			if category == "Sales Tax":
				agg["st_rate"] = rate
		elif category == FT_CATEGORY:
			agg["ft_amount"] += amount
			agg["ft_rate"] = rate
		elif category == AT_CATEGORY:
			agg["at_amount"] += amount

	for item in doc.get("items", []):
		agg = totals.get(item.name) or {}
		precision = item.precision("pk_st_amount") or 2
		item.pk_st_rate = flt(agg.get("st_rate", 0))
		item.pk_st_amount = flt(agg.get("st_amount", 0), precision)
		item.pk_further_tax_rate = flt(agg.get("ft_rate", 0))
		item.pk_further_tax_amount = flt(agg.get("ft_amount", 0), precision)
		item.pk_advance_tax_amount = flt(agg.get("at_amount", 0), precision)
		item.pk_total_incl_tax = flt(
			flt(item.net_amount) + item.pk_st_amount + item.pk_further_tax_amount,
			precision)
