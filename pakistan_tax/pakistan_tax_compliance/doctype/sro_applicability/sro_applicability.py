# Copyright (c) 2026, SpotLedger
# For license information, please see license.txt

"""SRO Applicability (plan §3.6) — the maintenance-job configuration.

A generator, not a runtime dependency: it writes dated Item Tax rows onto
matching items (blank tax_category = goods-level; set = buyer-level). The
native engine then resolves them by tax_category + valid_from. If this doctype
vanished tomorrow, invoices would still resolve correctly from the rows it
wrote. Expiry writes dated reversion rows — history is never deleted."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, now_datetime, nowdate


class SROApplicability(Document):
	def validate(self):
		if not self.scope:
			frappe.throw(_("Add at least one item scope row"))
		for row in self.scope:
			if not (row.hs_code_prefix or row.item_group or row.item):
				frappe.throw(_(
					"Scope row #{0}: set an HS code prefix, item group or item"
				).format(row.idx))
		if self.sro and self.sro_item_serial:
			if not frappe.db.exists("FBR SRO Item",
					{"sro": self.sro, "sro_item_serial": self.sro_item_serial}):
				frappe.throw(_("SRO item serial {0} does not exist under {1}").format(
					self.sro_item_serial, self.sro))

	def matching_items(self):
		names = set()
		for row in self.scope:
			if row.item:
				names.add(row.item)
			if row.item_group:
				names.update(frappe.get_all("Item",
					filters={"item_group": row.item_group}, pluck="name"))
			if row.hs_code_prefix:
				names.update(frappe.get_all("Item",
					filters={"customs_tariff_number":
						("like", f"{row.hs_code_prefix}%")}, pluck="name"))
		return sorted(names)

	def _target_template(self):
		"""The generated template for the concession tuple; create if missing."""
		existing = frappe.db.get_value("Item Tax Template", {
			"company": self.company,
			"pk_fbr_transaction_type": self.transaction_type,
			"pk_fbr_rate": self.fbr_rate})
		if existing:
			return existing

		from pakistan_tax.tax_config.accounts import ensure_tax_accounts
		from pakistan_tax.tax_config.template_generator import (
			_rate_rows, _template_title)
		settings = ensure_tax_accounts(self.company)
		rate = frappe.get_doc("FBR Rate", self.fbr_rate)
		if rate.needs_review:
			frappe.throw(_(
				"FBR Rate {0} needs review before templates can be generated"
			).format(rate.name))
		tt_id = frappe.db.get_value("FBR Transaction Type", self.transaction_type,
			"transaction_type_id")
		doc = frappe.get_doc({
			"doctype": "Item Tax Template",
			"title": _template_title(tt_id, rate.rate_id, rate.rate_desc),
			"company": self.company,
			"pk_fbr_transaction_type": self.transaction_type,
			"pk_fbr_rate": self.fbr_rate,
			"pk_is_fbr_generated": 1,
			"taxes": _rate_rows(rate, settings),
		})
		doc.insert(ignore_permissions=True)
		return doc.name

	@frappe.whitelist()
	def apply(self):
		"""Ensure every matching item carries the dated concession tax row."""
		if not self.enabled or self.retired:
			return {"applied": 0, "skipped": "disabled or retired"}
		template = self._target_template()
		category = self.tax_category or ""
		applied = 0
		for item_code in self.matching_items():
			item = frappe.get_doc("Item", item_code)
			exists = any(
				r.item_tax_template == template
				and (r.tax_category or "") == category
				and str(r.valid_from or "") == str(self.valid_from)
				for r in item.get("taxes", []))
			if exists:
				continue
			item.append("taxes", {
				"item_tax_template": template,
				"tax_category": self.tax_category,
				"valid_from": self.valid_from,
			})
			item.flags.ignore_permissions = True
			item.save()
			applied += 1
		self.db_set("last_applied", now_datetime(), update_modified=False)
		self.db_set("items_affected", len(self.matching_items()),
			update_modified=False)
		return {"applied": applied, "template": template}

	@frappe.whitelist()
	def retire(self):
		"""Write dated reversion rows: from valid_upto + 1 the item's own
		transaction-type default template applies again."""
		if not self.valid_upto:
			frappe.throw(_("Set Valid Upto before retiring"))
		from pakistan_tax.transactions.resolution import _from_transaction_type
		template = frappe.db.get_value("Item Tax Template", {
			"company": self.company,
			"pk_fbr_transaction_type": self.transaction_type,
			"pk_fbr_rate": self.fbr_rate})
		category = self.tax_category or ""
		revert_date = add_days(getdate(self.valid_upto), 1)
		reverted, skipped = 0, []
		for item_code in self.matching_items():
			item = frappe.get_doc("Item", item_code)
			has_concession = any(r.item_tax_template == template
				and (r.tax_category or "") == category
				for r in item.get("taxes", []))
			if not has_concession:
				continue
			already = any((r.tax_category or "") == category
				and r.valid_from and getdate(r.valid_from) >= revert_date
				for r in item.get("taxes", []))
			if already:
				continue
			default = _from_transaction_type(
				item.get("pk_fbr_transaction_type"), self.company, revert_date)
			if not default:
				skipped.append(item_code)
				continue
			item.append("taxes", {
				"item_tax_template": default,
				"tax_category": self.tax_category,
				"valid_from": revert_date,
			})
			item.flags.ignore_permissions = True
			item.save()
			reverted += 1
		self.db_set("retired", 1, update_modified=False)
		if skipped:
			frappe.msgprint(_(
				"No default template found for: {0} — set their FBR Transaction "
				"Type and re-run retire").format(", ".join(skipped)))
		return {"reverted": reverted, "skipped": skipped}


def apply_all():
	"""Daily scheduler: apply active applicabilities, retire expired ones."""
	today = getdate(nowdate())
	for name in frappe.get_all("SRO Applicability",
			filters={"enabled": 1, "retired": 0}, pluck="name"):
		doc = frappe.get_doc("SRO Applicability", name)
		try:
			if doc.valid_upto and getdate(doc.valid_upto) < today:
				doc.retire()
			else:
				doc.apply()
		except Exception:
			frappe.log_error(title=f"SRO Applicability {name} failed",
				message=frappe.get_traceback())


def find_sro_for_row(item_code, company, tax_category, posting_date, template):
	"""Resolution helper: the SRO/serial belonging to the applicability that
	produced this row's template (goods-level rows win only if no buyer-level
	applicability matches)."""
	apps = frappe.get_all("SRO Applicability",
		filters={"company": company, "enabled": 1, "sro": ("is", "set")},
		fields=["name", "tax_category", "sro", "sro_item_serial", "valid_from",
			"valid_upto", "transaction_type", "fbr_rate"])
	d = getdate(posting_date)
	best = None
	for app in apps:
		if getdate(app.valid_from) > d:
			continue
		if app.valid_upto and d > getdate(app.valid_upto):
			continue
		if app.tax_category and app.tax_category != (tax_category or ""):
			continue
		app_template = frappe.db.get_value("Item Tax Template", {
			"company": company,
			"pk_fbr_transaction_type": app.transaction_type,
			"pk_fbr_rate": app.fbr_rate})
		if app_template != template:
			continue
		doc = frappe.get_doc("SRO Applicability", app.name)
		if item_code not in doc.matching_items():
			continue
		if app.tax_category or best is None:
			best = app
	return best
