# Copyright (c) 2026, SpotLedger
"""Per-company tax account structure (plan §3.2/§3.3).

One account per direction (Input / Output) regardless of how the rate was
computed — percentage, fixed per-unit, or compound (both at once). The GL
doesn't need to know which; that's tracked on the invoice line via
item_tax_template + the rate fields. Percentage components still post via
the native engine's item_tax_rate override; fixed/per-unit components post
via a staged Actual amount (transactions/fixed_component.py) so both can
land on the very same account without the item-tax-map collision a second
Item Tax Template row on that account would cause (Item Tax Template
rejects two rows on one account outright)."""

import frappe
from frappe import _

OUTPUT_ACCOUNTS = [
	("account_sales_tax", "Sales Tax Payable"),
	("account_further_tax", "Further Sales Tax Payable"),
	("account_advance_tax_236g", "Advance Tax 236G Payable"),
]
INPUT_ACCOUNTS = [
	("account_input_sales_tax", "Input Sales Tax"),
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
