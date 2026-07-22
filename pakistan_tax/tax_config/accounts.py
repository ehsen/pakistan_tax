# Copyright (c) 2026, SpotLedger
"""Per-company tax account structure (plan §3.2/§3.3).

Distinct accounts per component because the item tax map is keyed by account:
a compound rate (18% + Rs.60/kg) needs its percentage and per-unit parts on
different accounts to be independently overridable per item.
"""

import frappe
from frappe import _

OUTPUT_ACCOUNTS = [
	("account_sales_tax", "Sales Tax Payable"),
	("account_sales_tax_fixed", "Sales Tax Payable - Fixed"),
	("account_further_tax", "Further Sales Tax Payable"),
	("account_advance_tax_236g", "Advance Tax 236G Payable"),
]
INPUT_ACCOUNTS = [
	("account_input_sales_tax", "Input Sales Tax"),
	("account_input_sales_tax_fixed", "Input Sales Tax - Fixed"),
]


def _find_parent(company, candidates, root_type):
	for candidate in candidates:
		name = frappe.db.get_value("Account",
			{"company": company, "account_name": candidate, "is_group": 1})
		if name:
			return name
	# fallback: first group account of the root type
	return frappe.db.get_value("Account",
		{"company": company, "root_type": root_type, "is_group": 1},
		order_by="lft")


def _ensure_account(company, account_name, parent, root_type):
	existing = frappe.db.get_value("Account",
		{"company": company, "account_name": account_name})
	if existing:
		return existing
	doc = frappe.get_doc({
		"doctype": "Account",
		"company": company,
		"account_name": account_name,
		"parent_account": parent,
		"account_type": "Tax",
		"root_type": root_type,
		"is_group": 0,
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_tax_accounts(company):
	"""Create missing tax accounts and record them on FBR Settings."""
	settings_name = frappe.db.get_value("FBR Settings", {"company": company})
	if not settings_name:
		frappe.throw(_("No FBR Settings for company {0}").format(company))
	settings = frappe.get_doc("FBR Settings", settings_name)

	liability_parent = _find_parent(company,
		["Duties and Taxes", "Current Liabilities"], "Liability")
	asset_parent = _find_parent(company,
		["Tax Assets", "Current Assets"], "Asset")

	updates = {}
	for field, account_name in OUTPUT_ACCOUNTS:
		acc = _ensure_account(company, account_name, liability_parent, "Liability")
		if not settings.get(field):
			updates[field] = acc
	for field, account_name in INPUT_ACCOUNTS:
		acc = _ensure_account(company, account_name, asset_parent, "Asset")
		if not settings.get(field):
			updates[field] = acc

	if updates:
		frappe.db.set_value("FBR Settings", settings_name, updates,
			update_modified=False)
		settings.reload()

	# all app-managed tax accounts are party-tracked by default (§3.8)
	for field, _account_name in OUTPUT_ACCOUNTS + INPUT_ACCOUNTS:
		account = settings.get(field)
		if account and not frappe.db.get_value("Account", account,
				"pk_track_party_wise"):
			frappe.db.set_value("Account", account, "pk_track_party_wise", 1,
				update_modified=False)
	frappe.clear_cache(doctype="Account")

	return settings
