# Copyright (c) 2026, SpotLedger
"""Posting client for FBR Digital Invoicing (doc §4.1/§4.2).

validate -> validateinvoicedata[_sb]; post -> postinvoicedata[_sb].
Every call is logged to FBR Api Log by the transport with the invoice as
reference. Success updates the invoice + its Tax Ledger Entries."""

import frappe
from frappe import _
from frappe.utils import now_datetime

from pakistan_tax.fbr.client import DI_DATA, FBRClient
from pakistan_tax.transactions.payload import build_payload


def _extract_errors(data):
	"""FBR returns HTTP 200 with statusCode '01' inside validationResponse."""
	errors = []
	if not isinstance(data, dict):
		return errors
	vr = data.get("validationResponse") or {}
	if vr.get("statusCode") == "01" or "invalid" in (vr.get("status") or "").lower():
		if vr.get("error"):
			errors.append({"itemSNo": "-", "error": vr["error"],
				"errorCode": vr.get("errorCode")})
		for st in vr.get("invoiceStatuses") or []:
			if st.get("statusCode") == "01":
				errors.append({"itemSNo": st.get("itemSNo"),
					"error": st.get("error"), "errorCode": st.get("errorCode")})
	return errors


def _format_errors(errors):
	lines = [_("FBR validation errors:")]
	for e in errors:
		lines.append(f"  Item {e.get('itemSNo')}: [{e.get('errorCode') or '-'}] "
			f"{e.get('error') or ''}")
	return "\n".join(lines)


def _call(invoice_name, endpoint_leaf):
	si = frappe.get_doc("Sales Invoice", invoice_name)
	if si.docstatus != 1:
		frappe.throw(_("Sales Invoice must be submitted before FBR filing"))
	client = FBRClient(company=si.company)
	sandbox = client.settings.environment == "Sandbox"
	payload = build_payload(si, for_sandbox=sandbox)
	suffix = "_sb" if sandbox else ""
	url = f"{DI_DATA}/{endpoint_leaf}{suffix}"
	resp = client.post(url, payload=payload,
		reference_doctype="Sales Invoice", reference_name=invoice_name)
	return si, resp, payload


@frappe.whitelist()
def validate_with_fbr(invoice_name):
	frappe.only_for(("System Manager", "Accounts Manager", "Accounts User"))
	si, resp, payload = _call(invoice_name, "validateinvoicedata")
	errors = _extract_errors(resp.data)
	return {
		"success": resp.ok and not errors,
		"status_code": resp.status_code,
		"errors": errors,
		"error_text": _format_errors(errors) if errors else "",
		"response": resp.data,
	}


@frappe.whitelist()
def post_to_fbr(invoice_name):
	frappe.only_for(("System Manager", "Accounts Manager", "Accounts User"))
	si = frappe.get_doc("Sales Invoice", invoice_name)
	client = FBRClient(company=si.company)
	sandbox = client.settings.environment == "Sandbox"

	if not sandbox and si.get("pk_fbr_posting_status") == "Posted":
		return {"success": False, "already_posted": True,
			"fbr_invoice_number": si.pk_fbr_invoice_number}

	si, resp, payload = _call(invoice_name, "postinvoicedata")
	errors = _extract_errors(resp.data)

	if resp.ok and not errors:
		fbr_number = (resp.data or {}).get("invoiceNumber")
		frappe.db.set_value("Sales Invoice", invoice_name, {
			"pk_fbr_invoice_number": fbr_number,
			"pk_fbr_posting_status": "Posted",
			"pk_fbr_posting_date": now_datetime(),
		}, update_modified=False)
		# stamp the subledger with the FBR number
		for tle in frappe.get_all("Tax Ledger Entry",
				filters={"voucher_type": "Sales Invoice",
					"voucher_no": invoice_name}, pluck="name"):
			frappe.db.set_value("Tax Ledger Entry", tle, "fbr_invoice_no",
				fbr_number, update_modified=False)
		return {"success": True, "fbr_invoice_number": fbr_number,
			"response": resp.data}

	frappe.db.set_value("Sales Invoice", invoice_name,
		"pk_fbr_posting_status", "Failed", update_modified=False)
	return {"success": False, "status_code": resp.status_code,
		"errors": errors, "error_text": _format_errors(errors) if errors else resp.text,
		"response": resp.data}
