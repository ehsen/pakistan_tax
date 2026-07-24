# Copyright (c) 2026, SpotLedger
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class WHTRate(Document):
	def validate(self):
		self.title = f"{self.section} — {self.condition}"
		if self.valid_upto and getdate(self.valid_upto) < getdate(
				self.valid_from or "1900-01-01"):
			frappe.throw(_("Valid Upto cannot be before Valid From"))
		if self.not_a_flat_rate:
			self.filer_rate = 0
			self.non_filer_rate = 0
		self.validate_no_overlap()

	def validate_no_overlap(self):
		"""Only one rate per (section, condition) may cover any given date —
		mirrors the same guard on FBR Transaction Type Rate."""
		others = frappe.get_all("WHT Rate", filters={
			"section": self.section, "condition": self.condition,
			"name": ("!=", self.name or ""),
		}, fields=["name", "valid_from", "valid_upto"])
		start = getdate(self.valid_from) if self.valid_from else None
		end = getdate(self.valid_upto) if self.valid_upto else None
		for row in others:
			o_start = getdate(row.valid_from) if row.valid_from else None
			o_end = getdate(row.valid_upto) if row.valid_upto else None
			if start is None or o_start is None:
				continue  # undated rows are treated as always-open; skip strict check
			if (end is None or o_start <= end) and (o_end is None or start <= o_end):
				frappe.throw(_(
					"Validity overlaps with existing rate {0} for the same "
					"section and condition").format(row.name))

	def on_update(self):
		_recount_section(self.section)

	def on_trash(self):
		# on_trash fires before the row is actually removed — subtract self
		if frappe.db.exists("WHT Section", self.section):
			count = max(frappe.db.count("WHT Rate", {"section": self.section}) - 1, 0)
			frappe.db.set_value("WHT Section", self.section, "rate_count", count,
				update_modified=False)


def _recount_section(section):
	count = frappe.db.count("WHT Rate", {"section": section})
	if frappe.db.exists("WHT Section", section):
		frappe.db.set_value("WHT Section", section, "rate_count", count,
			update_modified=False)
