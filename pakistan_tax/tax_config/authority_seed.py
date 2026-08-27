# Copyright (c) 2026, SpotLedger
"""Seeds the Tax Authority master (plan §3.10 in PAKISTAN_TAX_APP_PLAN.md).

Idempotent — existing authority_code records are left untouched, same
pattern as pakistan_tax.wht.seed._seed()."""

import frappe

AUTHORITIES = [
	{"authority_code": "FBR", "authority_name": "Federal Board of Revenue",
		"jurisdiction_type": "Federal"},
	{"authority_code": "SRB", "authority_name": "Sindh Revenue Board",
		"jurisdiction_type": "Provincial"},
	{"authority_code": "PRA", "authority_name": "Punjab Revenue Authority",
		"jurisdiction_type": "Provincial"},
	{"authority_code": "KPRA", "authority_name": "Khyber Pakhtunkhwa Revenue Authority",
		"jurisdiction_type": "Provincial"},
	{"authority_code": "BRA", "authority_name": "Balochistan Revenue Authority",
		"jurisdiction_type": "Provincial"},
]


def _seed():
	created = 0
	for row in AUTHORITIES:
		if frappe.db.exists("Tax Authority", row["authority_code"]):
			continue
		frappe.get_doc({
			"doctype": "Tax Authority",
			"is_active": 1,
			**row,
		}).insert(ignore_permissions=True)
		created += 1
	return created
