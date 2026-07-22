# Copyright (c) 2026, SpotLedger
"""PRA (Punjab Revenue Authority) POS invoice registration — slim port of the
fbr_digital_invoicing flow. Graceful-degradation pattern retained: a PRA
failure never blocks invoice submission; status stays Pending for retry.

UNTESTED against a live PRA endpoint — exercise in staging before relying on it.
"""

import json

import frappe
import requests
from frappe import _
from frappe.utils import flt, now_datetime

TIMEOUT = 30


def _get_settings(company):
	name = frappe.db.get_value("PRA Settings", {"company": company, "is_enabled": 1})
	return frappe.get_doc("PRA Settings", name) if name else None


def _build_pra_payload(si, settings):
	items = []
	for row in si.items:
		items.append({
			"ItemCode": row.item_code,
			"ItemName": row.item_name,
			"Quantity": abs(flt(row.stock_qty) or flt(row.qty)),
			"PCTCode": (frappe.db.get_value("Item", row.item_code,
				"customs_tariff_number") or "").replace(".", "")[:8],
			"TaxRate": flt(row.pk_st_rate),
			"SaleValue": abs(flt(row.net_amount)),
			"TaxCharged": abs(flt(row.pk_st_amount)),
			"TotalAmount": abs(flt(row.pk_total_incl_tax)),
			"InvoiceType": 1,
		})
	return {
		"InvoiceNumber": "",
		"POSID": settings.pos_id,
		"USIN": si.name,
		"DateTime": str(si.posting_date),
		"BuyerName": si.customer_name,
		"BuyerPNTN": "", "BuyerCNIC": "", "BuyerPhoneNumber": "",
		"TotalSaleValue": abs(flt(si.base_net_total)),
		"TotalTaxCharged": abs(flt(sum(flt(r.pk_st_amount) for r in si.items))),
		"TotalBillAmount": abs(flt(si.base_grand_total)),
		"TotalQuantity": abs(flt(sum(flt(r.qty) for r in si.items))),
		"PaymentMode": 1,
		"InvoiceType": 1,
		"Items": items,
	}


def register_invoice(si, settings=None, timeout=TIMEOUT):
	settings = settings or _get_settings(si.company)
	if not settings:
		return {"success": False, "error": "PRA Settings not configured"}
	token = settings.get_password("auth_token", raise_exception=False)
	headers = {"Content-Type": "application/json"}
	if token:
		headers["Authorization"] = f"Bearer {token}"
	payload = _build_pra_payload(si, settings)
	try:
		resp = requests.post(settings.api_url, json=payload, headers=headers,
			timeout=timeout)
		data = None
		try:
			data = resp.json()
		except ValueError:
			pass
		frappe.get_doc({
			"doctype": "FBR Api Log", "endpoint": settings.api_url,
			"method": "POST", "reference_doctype": "Sales Invoice",
			"reference_name": si.name, "status_code": resp.status_code,
			"success": 1 if resp.status_code == 200 else 0,
			"request_payload": json.dumps(payload, indent=1, default=str),
			"response_payload": json.dumps(data, indent=1, default=str)
				if data else resp.text[:5000],
		}).insert(ignore_permissions=True)
		if resp.status_code == 200 and data and data.get("InvoiceNumber"):
			return {"success": True, "invoice_number": data["InvoiceNumber"]}
		return {"success": False, "error": resp.text[:500]}
	except requests.Timeout:
		return {"success": False, "timeout": True, "error": "PRA request timed out"}
	except requests.RequestException as e:
		return {"success": False, "error": str(e)}


def before_submit(doc, method=None):
	"""POS invoices only; failure never blocks submission."""
	if not doc.get("is_pos"):
		return
	settings = _get_settings(doc.company)
	if not settings:
		return
	if doc.get("pk_pra_invoice_number"):
		return
	result = register_invoice(doc, settings)
	if result.get("success"):
		doc.pk_pra_invoice_number = result["invoice_number"]
		doc.pk_pra_posting_status = "Posted"
	else:
		doc.pk_pra_posting_status = "Pending"
		frappe.msgprint(
			_("PRA registration pending: {0}. Invoice will submit; retry from "
			"the form.").format(result.get("error", "")),
			indicator="orange", alert=True)


@frappe.whitelist()
def retry_registration(invoice_name):
	frappe.only_for(("System Manager", "Accounts Manager", "Accounts User"))
	si = frappe.get_doc("Sales Invoice", invoice_name)
	if si.get("pk_pra_invoice_number"):
		return {"success": True, "already_registered": True}
	result = register_invoice(si)
	if result.get("success"):
		frappe.db.set_value("Sales Invoice", invoice_name, {
			"pk_pra_invoice_number": result["invoice_number"],
			"pk_pra_posting_status": "Posted",
		}, update_modified=False)
	return result
