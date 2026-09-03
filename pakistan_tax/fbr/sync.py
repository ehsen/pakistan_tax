# Copyright (c) 2026, SpotLedger
"""Snapshot-diff sync of FBR reference data into dated local doctypes.

FBR's reference APIs are point-in-time queries; validity intervals are
reconstructed locally: rows are opened when first seen, `last_seen_on` is
stamped on every sync, and rows are closed (valid_upto) when they stop
appearing. Nothing is edited or deleted — history accumulates.
"""

import json
import re
import time

import frappe
from frappe.utils import getdate, now_datetime, nowdate

from pakistan_tax.fbr.client import FBRClient

RATE_LIMIT_SLEEP = 0.4  # FBR allows max 3 calls/second


def _fbr_date(date=None):
	"""FBR reference APIs expect dd-Mon-YYYY."""
	return getdate(date or nowdate()).strftime("%d-%b-%Y")


# ---------------------------------------------------------------- provinces

def sync_provinces(client=None):
	client = client or FBRClient()
	resp = client.provinces()
	if not resp.ok:
		frappe.throw(f"Province sync failed: HTTP {resp.status_code}")
	count = 0
	for row in resp.data:
		code, name = row.get("stateProvinceCode"), (row.get("stateProvinceDesc") or "").strip()
		if not name:
			continue
		existing = frappe.db.get_value("FBR Province", {"province_code": code})
		if existing:
			frappe.db.set_value("FBR Province", existing, "province_name", name,
				update_modified=False)
		else:
			frappe.get_doc({"doctype": "FBR Province", "province_name": name,
				"province_code": code}).insert(ignore_permissions=True)
			count += 1
	return {"inserted": count, "total": len(resp.data)}


# ------------------------------------------------------- transaction types

def sync_transaction_types(client=None):
	client = client or FBRClient()
	resp = client.transaction_types()
	if not resp.ok:
		frappe.throw(f"Transaction type sync failed: HTTP {resp.status_code}")
	count = 0
	for row in resp.data:
		tid = row.get("transactioN_TYPE_ID")
		desc = (row.get("transactioN_DESC") or "").strip()
		if not desc:
			continue
		existing = frappe.db.get_value("FBR Transaction Type", {"transaction_type_id": tid})
		if existing:
			continue  # description is the docname; renames handled manually if FBR ever rewords
		frappe.get_doc({
			"doctype": "FBR Transaction Type",
			"transaction_type_id": tid,
			"transaction_description": desc,
		}).insert(ignore_permissions=True)
		count += 1
	return {"inserted": count, "total": len(resp.data)}


def seed_scenarios():
	"""Stamp sandbox scenario IDs (doc §9) onto transaction types."""
	from pakistan_tax.transactions.payload import SCENARIO_MAP
	updated = 0
	for desc, scenario in SCENARIO_MAP.items():
		name = frappe.db.get_value("FBR Transaction Type",
			{"transaction_description": desc})
		if name and not frappe.db.get_value("FBR Transaction Type", name, "scenario_id"):
			frappe.db.set_value("FBR Transaction Type", name, "scenario_id",
				scenario, update_modified=False)
			updated += 1
	return updated


# ------------------------------------------------------------------- UOMs

def sync_uoms(client=None):
	"""FBR UOM list becomes real UOM docs flagged custom_is_fbr_uom."""
	client = client or FBRClient()
	resp = client.uoms()
	if not resp.ok:
		frappe.throw(f"UOM sync failed: HTTP {resp.status_code}")
	count = 0
	for row in resp.data:
		uom_id, desc = row.get("uoM_ID"), (row.get("description") or "").strip()
		if not desc:
			continue
		if frappe.db.exists("UOM", desc):
			frappe.db.set_value("UOM", desc, {
				"custom_is_fbr_uom": 1, "custom_fbr_uom_id": uom_id,
			}, update_modified=False)
		else:
			doc = frappe.get_doc({"doctype": "UOM", "uom_name": desc, "enabled": 1})
			doc.insert(ignore_permissions=True)
			frappe.db.set_value("UOM", doc.name, {
				"custom_is_fbr_uom": 1, "custom_fbr_uom_id": uom_id,
			}, update_modified=False)
			count += 1
	return {"inserted": count, "total": len(resp.data)}


# ------------------------------------------------------------- rate parser

PERCENT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*%\s*$")
COMPOUND_RE = re.compile(
	r"^\s*(\d+(?:\.\d+)?)\s*%\s*along\s*with\s*rupees\s*(\d+(?:\.\d+)?)\s*per\s*([\w ]+?)\s*$",
	re.IGNORECASE,
)
# "Rs.700/MT", "Rs.250", "200/bill", "100/SqY", "Rs.1000"
FIXED_RE = re.compile(
	r"^\s*(?:Rs\.?\s*)?(\d+(?:\.\d+)?)\s*(?:/\s*([\w ]+?))?\s*$", re.IGNORECASE)

# rate_desc unit token -> FBR UOM doc name (extend as new tokens appear)
UOM_WORDS = {
	"kilogram": "KG", "kg": "KG", "litre": "Liter", "liter": "Liter",
	"mt": "MT", "ton": "MT", "sqy": "Square Yard", "set": "SET",
	"kwh": "KWH", "bill": "Bill",
}


def _resolve_uom(token):
	"""Map a rate_desc unit token to a UOM doc name — prefer an FBR-flagged UOM
	matching the token exactly, then the alias map, then any existing UOM."""
	if not token:
		return None
	token = token.strip()
	exact_fbr = frappe.db.get_value("UOM", {"name": token, "custom_is_fbr_uom": 1})
	if exact_fbr:
		return exact_fbr
	candidate = UOM_WORDS.get(token.lower(), token)
	fbr_alias = frappe.db.get_value("UOM", {"name": candidate, "custom_is_fbr_uom": 1})
	if fbr_alias:
		return fbr_alias
	return frappe.db.get_value("UOM", {"name": candidate})


def parse_rate_desc(desc, rate_value=0):
	"""Decompose a ratE_DESC string.

	Fixed rates (Rs.700/MT, 100/SqY, Rs.1000) are deterministic: a per-quantity
	amount charged via On Item Quantity, in the unit named (or the item's FBR
	UOM when unit is omitted). needs_review is reserved for descriptions that
	genuinely don't parse (e.g. "DTRE").
	"""
	desc = (desc or "").strip()
	out = {"rate_type": "", "percent_component": 0, "fixed_component": 0,
		"fixed_uom": None, "fixed_unit_label": None, "needs_review": 0}

	if desc.lower() == "exempt":
		out["rate_type"] = "Exempt"
		return out

	m = PERCENT_RE.match(desc)
	if m:
		pct = float(m.group(1))
		out["rate_type"] = "Zero" if pct == 0 else "Percentage"
		out["percent_component"] = pct
		return out

	m = COMPOUND_RE.match(desc)
	if m:
		out["rate_type"] = "Compound"
		out["percent_component"] = float(m.group(1))
		out["fixed_component"] = float(m.group(2))
		out["fixed_unit_label"] = m.group(3).strip()
		out["fixed_uom"] = _resolve_uom(out["fixed_unit_label"])
		return out

	m = FIXED_RE.match(desc)
	if m and ("rs" in desc.lower() or m.group(2)):
		# Require Rs-prefix or a /unit suffix so a bare number is never
		# silently classified (bare percentages always carry '%').
		out["rate_type"] = "Fixed"
		out["fixed_component"] = float(m.group(1))
		out["fixed_unit_label"] = (m.group(2) or "").strip() or None
		out["fixed_uom"] = _resolve_uom(out["fixed_unit_label"])
		return out

	# Anything else ("DTRE", free text): flag for one-time human decomposition
	out["needs_review"] = 1
	return out


def upsert_fbr_rate(rate_row):
	rate_id = rate_row.get("ratE_ID")
	desc = (rate_row.get("ratE_DESC") or "").strip()
	value = rate_row.get("ratE_VALUE") or 0
	name = frappe.db.get_value("FBR Rate", {"rate_id": rate_id})
	if name:
		frappe.db.set_value("FBR Rate", name, "last_seen_on", nowdate(),
			update_modified=False)
		return name
	parsed = parse_rate_desc(desc, value)
	fixed_uom = parsed.pop("fixed_uom", None)
	doc = frappe.get_doc({
		"doctype": "FBR Rate",
		"rate_id": rate_id,
		"rate_desc": desc,
		"last_seen_on": nowdate(),
		**parsed,
	})
	if fixed_uom and frappe.db.exists("UOM", fixed_uom):
		doc.fixed_uom = fixed_uom
	doc.insert(ignore_permissions=True)
	return doc.name


# ----------------------------------------------- rate associations (dated)

def _scope_provinces(settings):
	"""Provinces configured in FBR Settings; falls back to all synced provinces."""
	rows = [p.province for p in (settings.provinces or [])]
	if not rows:
		rows = frappe.get_all("FBR Province", pluck="name")
	out = []
	for name in rows:
		code = frappe.db.get_value("FBR Province", name, "province_code")
		if code is not None:
			out.append({"name": name, "code": code})
	return out


def sync_rates(client=None, for_date=None):
	"""SaleTypeToRate snapshot-diff for every (transaction type x scoped province)."""
	client = client or FBRClient()
	for_date = for_date or nowdate()
	fbr_date = _fbr_date(for_date)
	provinces = _scope_provinces(client.settings)
	trans_types = frappe.get_all("FBR Transaction Type",
		fields=["name", "transaction_type_id"])

	summary = {"opened": 0, "closed": 0, "refreshed": 0, "calls": 0, "changes": []}

	for prov in provinces:
		for tt in trans_types:
			resp = client.sale_type_to_rate(fbr_date, tt.transaction_type_id, prov["code"])
			summary["calls"] += 1
			time.sleep(RATE_LIMIT_SLEEP)
			if not resp.ok or not isinstance(resp.data, list):
				continue

			returned_rate_names = set()
			for rate_row in resp.data:
				returned_rate_names.add(upsert_fbr_rate(rate_row))

			open_rows = frappe.get_all("FBR Transaction Type Rate",
				filters={"transaction_type": tt.name, "province": prov["name"],
					"valid_upto": ("is", "not set")},
				fields=["name", "fbr_rate", "last_seen_on"])
			open_by_rate = {r.fbr_rate: r for r in open_rows}

			is_single = len(returned_rate_names) == 1
			for rate_name in returned_rate_names:
				if rate_name in open_by_rate:
					frappe.db.set_value("FBR Transaction Type Rate",
						open_by_rate[rate_name].name, "last_seen_on", for_date,
						update_modified=False)
					summary["refreshed"] += 1
				else:
					frappe.get_doc({
						"doctype": "FBR Transaction Type Rate",
						"transaction_type": tt.name,
						"province": prov["name"],
						"fbr_rate": rate_name,
						"valid_from": for_date,
						"is_default": 1 if is_single else 0,
						"source": "Synced",
						"last_seen_on": for_date,
					}).insert(ignore_permissions=True)
					summary["opened"] += 1
					summary["changes"].append(
						f"OPENED {tt.name} / {prov['name']} / {rate_name}")

			for rate_name, row in open_by_rate.items():
				if rate_name not in returned_rate_names:
					frappe.db.set_value("FBR Transaction Type Rate", row.name,
						"valid_upto", row.last_seen_on or for_date, update_modified=False)
					summary["closed"] += 1
					summary["changes"].append(
						f"CLOSED {tt.name} / {prov['name']} / {rate_name}")

	if summary["changes"]:
		frappe.log_error(title="FBR rate changes detected",
			message="\n".join(summary["changes"]))
	return summary


# ------------------------------------------------------- SRO chain (dated)

def sync_sro_chain(client=None, for_date=None):
	"""For every open rate association: SroSchedule -> FBR SRO (+ dated schedule
	association) -> SROItem (dated)."""
	client = client or FBRClient()
	for_date = for_date or nowdate()
	fbr_date = _fbr_date(for_date)

	scoped = {p["name"] for p in _scope_provinces(client.settings)}
	pairs = frappe.get_all("FBR Transaction Type Rate",
		filters={"valid_upto": ("is", "not set"), "province": ("in", list(scoped))},
		fields=["fbr_rate", "province"])
	seen_pairs = {(p.fbr_rate, p.province) for p in pairs}

	summary = {"sro_opened": 0, "sro_closed": 0, "items_opened": 0, "calls": 0}
	synced_sros = set()

	for rate_name, prov_name in seen_pairs:
		rate_id = frappe.db.get_value("FBR Rate", rate_name, "rate_id")
		prov_code = frappe.db.get_value("FBR Province", prov_name, "province_code")
		resp = client.sro_schedule(rate_id, fbr_date, prov_code)
		summary["calls"] += 1
		time.sleep(RATE_LIMIT_SLEEP)
		returned_sros = set()
		if resp.ok and isinstance(resp.data, list):
			for row in resp.data:
				sro_id = row.get("srO_ID")
				desc = (row.get("srO_DESC") or "").strip()
				if sro_id is None:
					continue
				sro_name = frappe.db.get_value("FBR SRO", {"sro_id": sro_id})
				if not sro_name:
					sro_name = frappe.get_doc({"doctype": "FBR SRO", "sro_id": sro_id,
						"sro_desc": desc, "last_seen_on": for_date}).insert(
						ignore_permissions=True).name
				else:
					frappe.db.set_value("FBR SRO", sro_name, "last_seen_on", for_date,
						update_modified=False)
				returned_sros.add(sro_name)

		open_rows = frappe.get_all("FBR SRO Schedule",
			filters={"fbr_rate": rate_name, "province": prov_name,
				"valid_upto": ("is", "not set")},
			fields=["name", "sro", "last_seen_on"])
		open_by_sro = {r.sro: r for r in open_rows}

		for sro_name in returned_sros:
			if sro_name in open_by_sro:
				frappe.db.set_value("FBR SRO Schedule", open_by_sro[sro_name].name,
					"last_seen_on", for_date, update_modified=False)
			else:
				frappe.get_doc({"doctype": "FBR SRO Schedule", "fbr_rate": rate_name,
					"province": prov_name, "sro": sro_name, "valid_from": for_date,
					"source": "Synced", "last_seen_on": for_date}).insert(
					ignore_permissions=True)
				summary["sro_opened"] += 1
		for sro_name, row in open_by_sro.items():
			if sro_name not in returned_sros:
				frappe.db.set_value("FBR SRO Schedule", row.name, "valid_upto",
					row.last_seen_on or for_date, update_modified=False)
				summary["sro_closed"] += 1

		# SRO items for every SRO currently open anywhere (once per sync)
		for sro_name in returned_sros:
			if sro_name in synced_sros:
				continue
			synced_sros.add(sro_name)
			sro_id = frappe.db.get_value("FBR SRO", sro_name, "sro_id")
			iresp = client.sro_items(str(getdate(for_date)), sro_id)
			summary["calls"] += 1
			time.sleep(RATE_LIMIT_SLEEP)
			if not iresp.ok or not isinstance(iresp.data, list):
				continue
			for item in iresp.data:
				item_id = item.get("srO_ITEM_ID")
				if item_id is None:
					continue
				existing = frappe.db.get_value("FBR SRO Item",
					{"sro": sro_name, "sro_item_id": item_id})
				if existing:
					frappe.db.set_value("FBR SRO Item", existing, "last_seen_on",
						for_date, update_modified=False)
				else:
					frappe.get_doc({"doctype": "FBR SRO Item", "sro": sro_name,
						"sro_item_id": item_id,
						"sro_item_serial": str(item.get("srO_ITEM_DESC") or ""),
						"valid_from": for_date, "last_seen_on": for_date}).insert(
						ignore_permissions=True)
					summary["items_opened"] += 1
	return summary


# ---------------------------------------------------------------- HS Code

def ensure_customs_tariff_number(hs_code, description=None):
	"""Item.customs_tariff_number is a Link — the record must exist."""
	if not frappe.db.exists("Customs Tariff Number", hs_code):
		frappe.get_doc({
			"doctype": "Customs Tariff Number",
			"tariff_number": hs_code,
			"description": description or hs_code,
		}).insert(ignore_permissions=True)
	return hs_code


def sync_hs_codes(rows=None, file_path=None, batch_size=200):
	"""Bulk create/update Customs Tariff Number records from a full HS code
	list (FBR's HS code reference export — a list of {hS_CODE, description}
	dicts; hs_code/description also accepted). Idempotent — safe to re-run
	whenever FBR publishes an updated list.

	Existing rows get their description updated only when it actually
	changed, so re-running this doesn't touch modified/unmodified timestamps
	for the other ~7000 unaffected rows.
	"""
	if rows is None:
		with open(file_path) as f:
			rows = json.load(f)

	existing = {
		row.name: row.description
		for row in frappe.db.get_all(
			"Customs Tariff Number", fields=["name", "description"], limit_page_length=0
		)
	}

	summary = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0, "total": len(rows)}
	for i, row in enumerate(rows, 1):
		hs_code = (row.get("hS_CODE") or row.get("hs_code") or "").strip()
		description = (row.get("description") or "").strip()
		if not hs_code:
			summary["skipped"] += 1
			continue

		if hs_code not in existing:
			frappe.get_doc({
				"doctype": "Customs Tariff Number",
				"tariff_number": hs_code,
				"description": description or hs_code,
			}).insert(ignore_permissions=True)
			summary["inserted"] += 1
		elif description and description != existing[hs_code]:
			frappe.db.set_value("Customs Tariff Number", hs_code, "description",
				description, update_modified=False)
			summary["updated"] += 1
		else:
			summary["unchanged"] += 1

		if i % batch_size == 0:
			frappe.db.commit()

	frappe.db.commit()
	return summary


def sync_hs_uom(hs_code, annexure_id=3, client=None):
	"""On-demand: fetch and cache the FBR-allowed UOM(s) for an HS code."""
	client = client or FBRClient()
	ensure_customs_tariff_number(hs_code)
	resp = client.hs_uom(hs_code, annexure_id)
	if not resp.ok or not isinstance(resp.data, list):
		return None
	results = []
	for row in resp.data:
		uom_id = row.get("uoM_ID")
		desc = (row.get("description") or "").strip()
		uom_name = frappe.db.get_value("UOM", {"custom_fbr_uom_id": uom_id}) or (
			desc if frappe.db.exists("UOM", desc) else None)
		existing = frappe.db.get_value("FBR HS UOM",
			{"hs_code": hs_code, "annexure_id": annexure_id})
		values = {"uom": uom_name, "fbr_uom_id": uom_id, "last_synced": now_datetime()}
		if existing:
			frappe.db.set_value("FBR HS UOM", existing, values, update_modified=False)
			results.append(existing)
		else:
			doc = frappe.get_doc({"doctype": "FBR HS UOM", "hs_code": hs_code,
				"annexure_id": annexure_id, **values})
			doc.insert(ignore_permissions=True)
			results.append(doc.name)
	return results


# ------------------------------------------------------------ orchestrator

@frappe.whitelist()
def sync_all():
	"""Full reference sync. Safe to run repeatedly (snapshot-diff)."""
	frappe.only_for("System Manager")
	client = FBRClient()
	out = {}
	out["provinces"] = sync_provinces(client)
	out["transaction_types"] = sync_transaction_types(client)
	out["uoms"] = sync_uoms(client)
	out["rates"] = sync_rates(client)
	out["sro"] = sync_sro_chain(client)
	return out


def daily_sync():
	"""Scheduler entry point — no-op unless an enabled FBR Settings exists.

	Reference data (provinces/transaction types/UOMs/rates/SRO chain) is
	global, so it's synced once. Item Tax Template generation is per-company
	(pk_is_fbr_generated templates carry a company), so it runs once per
	company with an enabled FBR Settings, isolated so one company's failure
	doesn't block another's."""
	companies = frappe.get_all("FBR Settings", filters={"is_enabled": 1}, pluck="company")
	if not companies:
		return
	try:
		client = FBRClient()
		sync_provinces(client)
		sync_transaction_types(client)
		sync_uoms(client)
		sync_rates(client)
		sync_sro_chain(client)
	except Exception:
		frappe.log_error(title="FBR daily sync failed", message=frappe.get_traceback())

	from pakistan_tax.tax_config.template_generator import (
		generate_item_tax_templates, update_transaction_type_defaults)

	for company in companies:
		try:
			generate_item_tax_templates(company)
			update_transaction_type_defaults(company)
		except Exception:
			frappe.log_error(title="FBR Item Tax Template generation failed",
				message=f"company={company}\n{frappe.get_traceback()}")
