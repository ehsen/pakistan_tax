# Copyright (c) 2026, SpotLedger
"""before_submit: pre-flight validation against the dated reference data,
then freeze the FBR tuple onto the rows (plan §3.5 snapshots).

Submitted documents are snapshots — payload and reports never re-resolve."""

import frappe
from frappe import _
from frappe.utils import getdate


def _association_covers(tt_name, rate_name, posting_date):
	rows = frappe.get_all("FBR Transaction Type Rate",
		filters={"transaction_type": tt_name, "fbr_rate": rate_name},
		fields=["valid_from", "valid_upto"])
	d = getdate(posting_date)
	for row in rows:
		if getdate(row.valid_from) <= d and (
				not row.valid_upto or d <= getdate(row.valid_upto)):
			return True
	return False


def validate_and_snapshot(doc, method=None):
	if not doc.get("pk_is_tax_invoice"):
		return

	is_sales = doc.doctype == "Sales Invoice"
	posting_date = doc.posting_date

	for row in doc.get("items", []):
		template_name = row.get("item_tax_template")
		if not template_name:
			frappe.throw(_(
				"Row #{0} ({1}): no Item Tax Template resolved. Set the item's "
				"FBR Transaction Type or pick a template, or untick "
				"'Sales Tax Invoice' if this document is not reported to FBR."
			).format(row.idx, row.item_code))

		meta = frappe.db.get_value("Item Tax Template", template_name,
			["pk_fbr_transaction_type", "pk_fbr_rate"], as_dict=True)
		if not meta or not meta.pk_fbr_rate:
			# manually built template without FBR metadata — allowed, no snapshot
			continue

		# dated association must cover the posting date
		if not _association_covers(meta.pk_fbr_transaction_type, meta.pk_fbr_rate,
				posting_date):
			frappe.throw(_(
				"Row #{0} ({1}): rate {2} is not valid for transaction type {3} "
				"on {4} per FBR reference data. Re-run the FBR sync or pick the "
				"correct dated template."
			).format(row.idx, row.item_code, meta.pk_fbr_rate,
				meta.pk_fbr_transaction_type, posting_date))

		# fixed-component rates must be invoiced in the item's stock UOM (§3.4)
		rate = frappe.db.get_value("FBR Rate", meta.pk_fbr_rate,
			["rate_type", "rate_desc"], as_dict=True)
		if rate.rate_type in ("Fixed", "Compound"):
			stock_uom = frappe.db.get_value("Item", row.item_code, "stock_uom")
			if row.uom != stock_uom:
				frappe.throw(_(
					"Row #{0} ({1}): rate '{2}' has a per-quantity component — "
					"this row must be invoiced in the stock UOM ({3}), not {4}."
				).format(row.idx, row.item_code, rate.rate_desc, stock_uom, row.uom))

		# SRO serial must belong to the selected SRO
		if row.get("pk_sro_schedule") and row.get("pk_sro_item_serial"):
			if not frappe.db.exists("FBR SRO Item", {
					"sro": row.pk_sro_schedule,
					"sro_item_serial": row.pk_sro_item_serial}):
				frappe.throw(_(
					"Row #{0}: SRO item serial {1} does not exist under {2}."
				).format(row.idx, row.pk_sro_item_serial, row.pk_sro_schedule))

		# ---- freeze the tuple ----
		row.pk_fbr_transaction_type = meta.pk_fbr_transaction_type
		row.pk_fbr_rate = meta.pk_fbr_rate
		row.pk_fbr_rate_desc = rate.rate_desc
		if not row.get("pk_sro_schedule"):
			row.pk_sro_schedule = frappe.db.get_value("Item", row.item_code,
				"pk_sro_schedule")
			row.pk_sro_item_serial = row.pk_sro_item_serial or frappe.db.get_value(
				"Item", row.item_code, "pk_sro_item_serial")

	# ---- buyer status snapshot (sales only) ----
	if is_sales:
		if doc.get("pk_tax_party"):
			tp = frappe.db.get_value("Tax Party", doc.pk_tax_party,
				["sales_tax_registration_type", "sales_tax_atl_status"], as_dict=True)
			doc.pk_buyer_reg_type_snapshot = tp.sales_tax_registration_type or "Unregistered"
			doc.pk_buyer_atl_snapshot = tp.sales_tax_atl_status or ""
		else:
			cust = frappe.db.get_value("Customer", doc.customer,
				["pk_sales_tax_registration_type", "pk_sales_tax_atl_status"],
				as_dict=True)
			doc.pk_buyer_reg_type_snapshot = (
				cust.pk_sales_tax_registration_type or "Unregistered")
			doc.pk_buyer_atl_snapshot = cust.pk_sales_tax_atl_status or ""
