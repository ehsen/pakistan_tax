# Copyright (c) 2026, SpotLedger
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class FBRHSUOM(Document):
	def validate(self):
		if frappe.db.exists("FBR HS UOM", {
			"hs_code": self.hs_code,
			"annexure_id": self.annexure_id,
			"name": ("!=", self.name or ""),
		}):
			frappe.throw(_("FBR HS UOM already exists for HS Code {0}").format(self.hs_code))
