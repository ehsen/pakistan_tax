# Copyright (c) 2026, SpotLedger
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CPRDeposit(Document):
	@frappe.whitelist()
	def get_entries(self):
		"""Pull all Withheld WHT-payable TLE rows for the period/section."""
		filters = {
			"company": self.company,
			"tax_type": "WHT Payable",
			"status": "Withheld",
			"posting_date": ("between", [self.from_date, self.to_date]),
		}
		if self.section:
			filters["section"] = self.section
		if self.tax_authority:
			filters["tax_authority"] = self.tax_authority

		self.items = []
		total = 0
		for row in frappe.get_all("Tax Ledger Entry", filters=filters,
				fields=["name", "party_type", "party", "section",
					"taxable_amount", "tax_amount"]):
			self.append("items", {
				"tax_ledger_entry": row.name,
				"party_type": row.party_type,
				"party": row.party,
				"section": row.section,
				"taxable_amount": row.taxable_amount,
				"tax_amount": row.tax_amount,
			})
			total += flt(row.tax_amount)
		self.total_tax = flt(total, 2)
		return len(self.items)

	def validate(self):
		self.total_tax = flt(sum(flt(i.tax_amount) for i in self.items), 2)

	def before_submit(self):
		if not self.cpr_number:
			frappe.throw(_("CPR Number is required before submitting the deposit"))
		if not self.items:
			frappe.throw(_("No withheld entries selected"))
		for item in self.items:
			status, tax_authority = frappe.db.get_value("Tax Ledger Entry",
				item.tax_ledger_entry, ["status", "tax_authority"])
			if status != "Withheld":
				frappe.throw(_(
					"Entry {0} is no longer in Withheld status ({1}) — refresh "
					"the entries").format(item.tax_ledger_entry, status))
			if self.tax_authority and tax_authority != self.tax_authority:
				frappe.throw(_(
					"Entry {0} belongs to {1}, not {2} — refresh the entries"
				).format(item.tax_ledger_entry, tax_authority, self.tax_authority))

	def on_submit(self):
		by_account = {}
		for item in self.items:
			account = frappe.db.get_value("WHT Section", item.section,
				"payable_account")
			by_account[account] = by_account.get(account, 0) + flt(item.tax_amount)

		je = frappe.get_doc({
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": self.company,
			"posting_date": self.posting_date,
			"user_remark": _("WHT deposit CPR {0} ({1} to {2})").format(
				self.cpr_number, self.from_date, self.to_date),
			"accounts": [
				*[{"account": account, "debit_in_account_currency": flt(amount, 2)}
					for account, amount in by_account.items()],
				{"account": self.bank_account,
					"credit_in_account_currency": flt(self.total_tax, 2)},
			],
		})
		je.insert(ignore_permissions=True)
		je.submit()
		self.db_set("journal_entry", je.name)

		for item in self.items:
			frappe.db.set_value("Tax Ledger Entry", item.tax_ledger_entry, {
				"status": "Deposited",
				"cpr_reference": self.cpr_number,
			}, update_modified=False)

	def on_cancel(self):
		for item in self.items:
			frappe.db.set_value("Tax Ledger Entry", item.tax_ledger_entry, {
				"status": "Withheld",
				"cpr_reference": None,
			}, update_modified=False)
		if self.journal_entry:
			je = frappe.get_doc("Journal Entry", self.journal_entry)
			if je.docstatus == 1:
				je.cancel()
