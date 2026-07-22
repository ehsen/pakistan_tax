# Copyright (c) 2026, SpotLedger
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

AMOUNT_TOLERANCE = 1.0  # rupee tolerance for rounding differences


class AnnexAImport(Document):
	@frappe.whitelist()
	def match_entries(self):
		"""Match FBR-declared purchase rows against Input ST subledger rows.

		Join key: supplier NTN + FBR invoice number. Outcomes per FBR row:
		Matched | Amount Mismatch | Missing In System. System rows with no
		FBR counterpart are stamped Missing (input at risk)."""
		tles = frappe.get_all("Tax Ledger Entry", filters={
			"company": self.company,
			"tax_type": "Input ST",
			"status": ("in", ["Claimed", "Matched", "Missing", "Mismatch"]),
			"posting_date": ("between", [self.period_start, self.period_end]),
			"is_reversal": 0,
		}, fields=["name", "party_ntn", "fbr_invoice_no", "tax_amount"])

		def norm(value):
			return (value or "").replace("-", "").replace(" ", "").strip().lower()

		by_key = {}
		for t in tles:
			by_key.setdefault((norm(t.party_ntn), norm(t.fbr_invoice_no)), []).append(t)

		matched = mismatch = missing = 0
		claimed_tle_names = {t.name for t in tles}
		seen_tles = set()

		for row in self.rows:
			key = (norm(row.supplier_ntn), norm(row.fbr_invoice_no))
			candidates = by_key.get(key) or []
			if not candidates:
				row.match_status = "Missing In System"
				row.matched_tle = None
				missing += 1
				continue
			tle = candidates[0]
			seen_tles.add(tle.name)
			if abs(flt(tle.tax_amount) - flt(row.sales_tax)) <= AMOUNT_TOLERANCE:
				row.match_status = "Matched"
				new_status = "Matched"
				matched += 1
			else:
				row.match_status = "Amount Mismatch"
				new_status = "Mismatch"
				mismatch += 1
			row.matched_tle = tle.name
			frappe.db.set_value("Tax Ledger Entry", tle.name, {
				"status": new_status, "match_reference": self.name,
			}, update_modified=False)

		at_risk = 0
		for name in claimed_tle_names - seen_tles:
			frappe.db.set_value("Tax Ledger Entry", name, {
				"status": "Missing", "match_reference": self.name,
			}, update_modified=False)
			at_risk += 1

		self.matched = matched
		self.amount_mismatch = mismatch
		self.missing_in_system = missing
		self.unclaimed_at_risk = at_risk
		self.save(ignore_permissions=True)
		return {"matched": matched, "mismatch": mismatch,
			"missing_in_system": missing, "at_risk": at_risk}
