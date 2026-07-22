# Copyright (c) 2026, SpotLedger
"""Party sales-tax status verification (STATL / Get_Reg_Type).

Three statuses exist in this domain; only the first two come from these APIs:
1. Sales Tax registration type (Registered/Unregistered)  <- Get_Reg_Type
2. Sales Tax ATL status (Active/In-Active)                <- statl
3. Income Tax filer status — different list entirely, NOT handled here.
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime, nowdate

from pakistan_tax.fbr.client import FBRClient


def normalize_regno(regno):
	"""Strip separators; FBR expects bare 7-char NTN or 13-digit CNIC."""
	return (regno or "").replace("-", "").replace(" ", "").strip()


def check_party_status(regno, client=None):
	"""Query both endpoints for a registration number. Returns dict.

	Get_Reg_Type returns a valid JSON body even on HTTP 500 — parse regardless.
	"""
	client = client or FBRClient()
	regno = normalize_regno(regno)
	if not regno:
		frappe.throw(_("No NTN/CNIC to verify"))

	result = {"regno": regno, "registration_type": "Unknown",
		"atl_status": "Unknown", "raw": {}}

	atl = client.statl(regno, str(nowdate()))
	if atl.data and isinstance(atl.data, dict):
		result["raw"]["statl"] = atl.data
		status = (atl.data.get("status") or "").strip().lower()
		if status in ("active", "in-active", "inactive"):
			result["atl_status"] = "Active" if status == "active" else "In-Active"

	reg = client.get_reg_type(regno)
	if reg.data and isinstance(reg.data, dict):
		result["raw"]["get_reg_type"] = reg.data
		reg_type = (reg.data.get("REGISTRATION_TYPE") or "").strip().lower()
		if reg_type in ("registered", "unregistered"):
			result["registration_type"] = reg_type.capitalize()

	return result


PARTY_FIELD_MAP = {
	# doctype: (regno source fields in priority order)
	"Customer": ("tax_id",),
	"Supplier": ("tax_id",),
	"Tax Party": ("ntn_cnic",),
	"Company": ("tax_id",),
}


@frappe.whitelist()
def verify_party(party_type, party):
	"""Verify one party against FBR, log it, and update cached status fields."""
	frappe.only_for(("System Manager", "Accounts Manager", "Accounts User"))
	if party_type not in PARTY_FIELD_MAP:
		frappe.throw(_("Unsupported party type {0}").format(party_type))

	doc = frappe.get_doc(party_type, party)
	regno = None
	for field in PARTY_FIELD_MAP[party_type]:
		regno = normalize_regno(doc.get(field))
		if regno:
			break
	if not regno:
		frappe.throw(_("{0} {1} has no NTN/CNIC set").format(party_type, party))

	result = check_party_status(regno)

	frappe.get_doc({
		"doctype": "FBR Party Status Log",
		"party_type": party_type,
		"party": party,
		"regno_sent": regno,
		"registration_type": result["registration_type"],
		"atl_status": result["atl_status"],
		"checked_on": now_datetime(),
		"source": "API",
		"raw_response": json.dumps(result["raw"], indent=1),
	}).insert(ignore_permissions=True)

	# Cache onto the party where the fields exist (Tax Party now;
	# Customer/Supplier custom fields arrive with the transaction phase)
	updates = {}
	if doc.meta.has_field("sales_tax_registration_type") and result["registration_type"] != "Unknown":
		updates["sales_tax_registration_type"] = result["registration_type"]
	if doc.meta.has_field("sales_tax_atl_status") and result["atl_status"] != "Unknown":
		updates["sales_tax_atl_status"] = result["atl_status"]
	if doc.meta.has_field("statl_last_verified"):
		updates["statl_last_verified"] = now_datetime()
	if updates:
		frappe.db.set_value(party_type, party, updates, update_modified=False)

	return result
