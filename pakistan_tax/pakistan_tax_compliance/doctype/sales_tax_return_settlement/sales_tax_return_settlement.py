# Copyright (c) 2026, SpotLedger
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class SalesTaxReturnSettlement(Document):
	def _tle_sum(self, tax_type, statuses):
		rows = frappe.get_all("Tax Ledger Entry", filters={
			"company": self.company,
			"tax_type": tax_type,
			"status": ("in", statuses),
			"posting_date": ("between", [self.period_start, self.period_end]),
		}, pluck="tax_amount")
		return flt(sum(flt(v) for v in rows))

	@frappe.whitelist()
	def compute(self):
		self.output_st = self._tle_sum("Output ST", ["Pending Return"])
		self.further_tax = self._tle_sum("Further Tax", ["Pending Return"])
		input_statuses = ["Matched"] if self.strict_input_matching else [
			"Claimed", "Matched"]
		input_total = self._tle_sum("Input ST", input_statuses)
		# input only offsets output ST — Further Tax is payable gross (s.3(1A))
		self.input_st_admissible = min(flt(input_total), flt(self.output_st))
		self.net_payable = flt(
			self.output_st - self.input_st_admissible + self.further_tax, 2)
		return {
			"output_st": self.output_st,
			"further_tax": self.further_tax,
			"input_st_admissible": self.input_st_admissible,
			"net_payable": self.net_payable,
		}

	def before_submit(self):
		self.compute()
		if not (self.output_st or self.further_tax):
			frappe.throw(_("Nothing to settle in this period"))

	def on_submit(self):
		settings = frappe.get_doc("FBR Settings",
			frappe.db.get_value("FBR Settings", {"company": self.company}))
		accounts = []
		if flt(self.output_st):
			accounts.append({"account": settings.account_sales_tax,
				"debit_in_account_currency": flt(self.output_st, 2)})
		if flt(self.further_tax):
			accounts.append({"account": settings.account_further_tax,
				"debit_in_account_currency": flt(self.further_tax, 2)})
		if flt(self.input_st_admissible):
			accounts.append({"account": settings.account_input_sales_tax,
				"credit_in_account_currency": flt(self.input_st_admissible, 2)})
		if flt(self.net_payable):
			accounts.append({"account": self.bank_account,
				"credit_in_account_currency": flt(self.net_payable, 2)})

		je = frappe.get_doc({
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": self.company,
			"posting_date": self.posting_date,
			"user_remark": _("Sales tax return settlement {0} to {1}").format(
				self.period_start, self.period_end),
			"accounts": accounts,
		})
		je.insert(ignore_permissions=True)
		je.submit()
		self.db_set("journal_entry", je.name)

		for tax_type, statuses in (
				("Output ST", ["Pending Return"]),
				("Further Tax", ["Pending Return"]),
				("Input ST", ["Claimed", "Matched"])):
			for name in frappe.get_all("Tax Ledger Entry", filters={
					"company": self.company, "tax_type": tax_type,
					"status": ("in", statuses),
					"posting_date": ("between",
						[self.period_start, self.period_end])}, pluck="name"):
				frappe.db.set_value("Tax Ledger Entry", name, {
					"status": "Settled", "match_reference": self.name,
				}, update_modified=False)

	def on_cancel(self):
		for name in frappe.get_all("Tax Ledger Entry",
				filters={"match_reference": self.name}, pluck="name"):
			row_type = frappe.db.get_value("Tax Ledger Entry", name, "tax_type")
			restored = "Claimed" if row_type == "Input ST" else "Pending Return"
			frappe.db.set_value("Tax Ledger Entry", name, {
				"status": restored, "match_reference": None,
			}, update_modified=False)
		if self.journal_entry:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			if je.docstatus == 1:
				je.cancel()
