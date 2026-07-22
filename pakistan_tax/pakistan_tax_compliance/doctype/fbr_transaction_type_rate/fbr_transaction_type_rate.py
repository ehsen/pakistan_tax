# Copyright (c) 2026, SpotLedger
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class FBRTransactionTypeRate(Document):
	def validate(self):
		self.validate_no_overlap()

	def validate_no_overlap(self):
		"""Only one row per (transaction_type, province, fbr_rate) may cover any given date."""
		others = frappe.get_all(
			"FBR Transaction Type Rate",
			filters={
				"transaction_type": self.transaction_type,
				"province": self.province,
				"fbr_rate": self.fbr_rate,
				"name": ("!=", self.name or ""),
			},
			fields=["name", "valid_from", "valid_upto"],
		)
		from frappe.utils import getdate
		start = getdate(self.valid_from)
		end = getdate(self.valid_upto) if self.valid_upto else None
		for row in others:
			o_start = getdate(row.valid_from)
			o_end = getdate(row.valid_upto) if row.valid_upto else None
			if (end is None or o_start <= end) and (o_end is None or start <= o_end):
				frappe.throw(_(
					"Validity overlaps with existing row {0} for the same transaction type, province and rate"
				).format(row.name))
