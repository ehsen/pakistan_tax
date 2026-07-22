# Copyright (c) 2026, SpotLedger
"""FBR Digital Invoicing payload builder (doc §4.1) — reads FROZEN snapshots
and engine-computed line fields off a submitted Sales Invoice. Never
re-resolves rates or statuses."""

import re

import frappe
from frappe import _
from frappe.utils import flt, getdate

from pakistan_tax.fbr.client import get_settings

# transaction descriptions whose sandbox scenario depends on buyer status
STANDARD_RATE_TT = "Goods at standard rate (default)"

SCENARIO_MAP = {
	"Steel melting and re-rolling": "SN003",
	"Ship breaking": "SN004",
	"Goods at Reduced Rate": "SN005",
	"Exempt goods": "SN006",
	"Goods at zero-rate": "SN007",
	"3rd Schedule Goods": "SN008",
	"Cotton ginners": "SN009",
	"Telecommunication services": "SN010",
	"Toll Manufacturing": "SN011",
	"Petroleum Products": "SN012",
	"Electricity Supply to Retailers": "SN013",
	"Gas to CNG stations": "SN014",
	"Mobile Phones": "SN015",
	"Processing/Conversion of Goods": "SN016",
	"Goods (FED in ST Mode)": "SN017",
	"Services (FED in ST Mode)": "SN018",
	"Services": "SN019",
	"Electric Vehicle": "SN020",
	"Cement /Concrete Block": "SN021",
	"Potassium Chlorate": "SN022",
	"CNG Sales": "SN023",
	"Goods as per SRO.297(|)/2023": "SN024",
	"Non-Adjustable Supplies": "SN025",
}


def normalize_regno(value):
	return (value or "").replace("-", "").replace(" ", "").strip()


def _validate_ntn_cnic(value, label):
	clean = normalize_regno(value)
	if not clean:
		return
	if len(clean) == 7 and clean.isalnum():
		return
	if len(clean) == 13 and clean.isdigit():
		return
	frappe.throw(_(
		"{0} NTN/CNIC must be 7 alphanumeric characters (NTN) or 13 digits "
		"(CNIC). Got: {1}").format(label, value))


def _seller(settings, company):
	name = settings.get("seller_business_name") or company
	ntn = normalize_regno(frappe.db.get_value("Company", company, "tax_id"))
	province = settings.get("seller_province")
	address = settings.get("seller_address")
	if not (ntn and province and address):
		frappe.throw(_(
			"Complete the seller profile on FBR Settings {0}: company NTN "
			"(Company.tax_id), Seller Province and Seller Address."
		).format(settings.name))
	return {
		"sellerNTNCNIC": ntn,
		"sellerBusinessName": name,
		"sellerProvince": province,
		"sellerAddress": address,
	}


def _buyer(si):
	if si.get("pk_tax_party"):
		tp = frappe.get_doc("Tax Party", si.pk_tax_party)
		return {
			"buyerNTNCNIC": normalize_regno(tp.ntn_cnic),
			"buyerBusinessName": tp.party_name,
			"buyerProvince": tp.province or "",
			"buyerAddress": tp.address or "",
			"buyerRegistrationType": si.get("pk_buyer_reg_type_snapshot")
				or tp.sales_tax_registration_type or "Unregistered",
		}
	cust = frappe.get_doc("Customer", si.customer)
	return {
		"buyerNTNCNIC": normalize_regno(cust.tax_id),
		"buyerBusinessName": cust.customer_name,
		"buyerProvince": cust.get("pk_fbr_province") or "",
		"buyerAddress": cust.get("pk_fbr_address") or "",
		"buyerRegistrationType": si.get("pk_buyer_reg_type_snapshot")
			or cust.get("pk_sales_tax_registration_type") or "Unregistered",
	}


def _scenario(si):
	"""Sandbox scenario from the first item's transaction type + buyer status."""
	tt = None
	for row in si.items:
		tt = row.get("pk_fbr_transaction_type")
		if tt:
			break
	if not tt or tt == STANDARD_RATE_TT:
		registered = (si.get("pk_buyer_reg_type_snapshot") == "Registered")
		return "SN001" if registered else "SN002"
	stored = frappe.db.get_value("FBR Transaction Type", tt, "scenario_id")
	return stored or SCENARIO_MAP.get(tt) or "SN001"


def _item_payload(si, row):
	item = frappe.db.get_value("Item", row.item_code,
		["customs_tariff_number", "pk_retail_price", "pk_fixed_notified_value",
			"stock_uom"], as_dict=True) or frappe._dict()

	tt = row.get("pk_fbr_transaction_type") or ""
	is_third_schedule = tt == "3rd Schedule Goods"
	qty = abs(flt(row.stock_qty) or flt(row.qty))

	value_excl = abs(flt(row.net_amount))
	notified_base = max(flt(item.pk_fixed_notified_value), flt(item.pk_retail_price))
	fixed_notified = flt(notified_base * qty) if is_third_schedule else flt(
		item.pk_fixed_notified_value or 0)
	if is_third_schedule:
		value_excl = fixed_notified

	sales_tax = abs(flt(row.pk_st_amount))
	further_tax = abs(flt(row.pk_further_tax_amount))
	total_values = flt(value_excl + sales_tax + further_tax)

	data = {
		"hsCode": item.customs_tariff_number or "",
		"productDescription": row.item_name or row.item_code,
		"rate": row.get("pk_fbr_rate_desc") or "",
		"uoM": row.get("stock_uom") or item.stock_uom or row.uom,
		"quantity": qty,
		"totalValues": total_values,
		"valueSalesExcludingST": value_excl,
		"fixedNotifiedValueOrRetailPrice": fixed_notified,
		"salesTaxApplicable": sales_tax,
		"salesTaxWithheldAtSource": 0.00,
		"extraTax": "" if tt == "Goods at Reduced Rate" else 0.00,
		"furtherTax": further_tax,
		"fedPayable": 0.00,
		"discount": 0.00,
		"saleType": tt,
	}
	if row.get("pk_sro_schedule"):
		data["sroScheduleNo"] = frappe.db.get_value("FBR SRO", row.pk_sro_schedule,
			"sro_desc")
		data["sroItemSerialNo"] = row.get("pk_sro_item_serial") or ""
	return data


def build_payload(sales_invoice, for_sandbox=None):
	si = (sales_invoice if isinstance(sales_invoice, frappe.model.document.Document)
		else frappe.get_doc("Sales Invoice", sales_invoice))
	if not si.get("pk_is_tax_invoice"):
		frappe.throw(_("{0} is not flagged as a Sales Tax Invoice").format(si.name))

	settings = get_settings(si.company)
	if for_sandbox is None:
		for_sandbox = settings.environment == "Sandbox"

	payload = {
		"invoiceType": "Debit Note" if si.is_return else "Sale Invoice",
		"invoiceDate": getdate(si.posting_date).strftime("%Y-%m-%d"),
		**_seller(settings, si.company),
		**_buyer(si),
		"invoiceRefNo": "",
		"items": [_item_payload(si, row) for row in si.items],
	}

	if si.is_return and si.return_against:
		ref = frappe.db.get_value("Sales Invoice", si.return_against,
			"pk_fbr_invoice_number")
		if not ref:
			frappe.throw(_(
				"Original invoice {0} has no FBR invoice number — a Debit Note "
				"cannot be filed before its original invoice.").format(si.return_against))
		payload["invoiceRefNo"] = ref

	if for_sandbox:
		payload["scenarioId"] = _scenario(si)

	# essential format checks before it leaves the building
	_validate_ntn_cnic(payload["sellerNTNCNIC"], "Seller")
	if payload["buyerRegistrationType"] == "Registered":
		if not payload["buyerNTNCNIC"]:
			frappe.throw(_("Registered buyer requires an NTN/CNIC"))
		_validate_ntn_cnic(payload["buyerNTNCNIC"], "Buyer")
	for idx, item in enumerate(payload["items"], 1):
		for field in ("productDescription", "rate", "uoM", "saleType"):
			if not item.get(field):
				frappe.throw(_("Item #{0}: missing {1}").format(idx, field))
		if item["hsCode"] and not re.match(r"^\d{4}\.\d{4}$|^\d{8}$", item["hsCode"]):
			frappe.throw(_("Item #{0}: HS code format must be XXXX.XXXX").format(idx))

	return payload
