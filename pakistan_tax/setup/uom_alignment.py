# Copyright (c) 2026, SpotLedger
"""Align the site's UOM master to FBR's canonical UOM list (§3.4 of the plan).

- FBR-synced UOMs are renamed to FBR's exact spelling (rename_doc rewrites
  every reference: items, conversions, historical transactions).
- Known ERPNext-default aliases are merged into their FBR equivalent.
- Remaining non-FBR UOMs that are unused anywhere get disabled (not deleted).
  Used non-FBR UOMs are left enabled — they are commercial/pack UOMs.
"""

import frappe

# ERPNext-default name -> FBR canonical name (merge targets must exist)
ALIASES = {
	"Nos": "Numbers, pieces, units",
	"Litre": "Liter",
	"Kg": "KG",
	"Meter": "Metre",
	"Square Meter": "Square Metre",
	"Set": "SET",
}


def _case_only_rename(old, new):
	"""MariaDB collation is case-insensitive; two-step rename via temp name."""
	tmp = f"{new}__uomtmp"
	frappe.rename_doc("UOM", old, tmp, force=True)
	frappe.rename_doc("UOM", tmp, new, force=True)


def _used_uoms():
	used = set()
	for query in (
		"select distinct stock_uom from tabItem where stock_uom is not null",
		"select distinct purchase_uom from tabItem where purchase_uom is not null",
		"select distinct sales_uom from tabItem where sales_uom is not null",
		"select distinct uom from `tabUOM Conversion Detail`",
		"select distinct uom from `tabSales Invoice Item`",
		"select distinct uom from `tabPurchase Invoice Item`",
		"select distinct uom from `tabStock Ledger Entry`",
	):
		try:
			used.update(x[0] for x in frappe.db.sql(query) if x and x[0])
		except Exception:
			pass
	return used


def align_uoms(verbose=True):
	out = {"renamed": [], "merged": [], "disabled": 0, "skipped": []}

	# 1. Exact-casing rename for FBR-synced UOMs (name should equal FBR desc)
	flagged = frappe.get_all("UOM", filters={"custom_is_fbr_uom": 1},
		fields=["name", "custom_fbr_uom_id"])
	from pakistan_tax.fbr.client import FBRClient
	resp = FBRClient().uoms()
	if not resp.ok:
		frappe.throw("Could not fetch FBR UOM list")
	fbr_by_id = {r["uoM_ID"]: (r["description"] or "").strip() for r in resp.data}

	for row in flagged:
		want = fbr_by_id.get(row.custom_fbr_uom_id)
		if not want or row.name == want:
			continue
		if row.name.lower() == want.lower():
			_case_only_rename(row.name, want)
			out["renamed"].append(f"{row.name} -> {want}")
		else:
			existing = frappe.db.get_value("UOM", {"name": want})
			if existing and existing != row.name:
				frappe.rename_doc("UOM", row.name, want, merge=True, force=True)
				out["merged"].append(f"{row.name} => {want}")
			else:
				frappe.rename_doc("UOM", row.name, want, force=True)
				out["renamed"].append(f"{row.name} -> {want}")

	# 2. Merge ERPNext-default aliases into FBR names
	for old, new in ALIASES.items():
		if not frappe.db.exists("UOM", old):
			continue
		# case-insensitive hit that is actually the same doc = already handled
		actual_old = frappe.db.get_value("UOM", {"name": old})
		if not actual_old or actual_old == new:
			continue
		if frappe.db.exists("UOM", new) and frappe.db.get_value("UOM", {"name": new}) != actual_old:
			frappe.rename_doc("UOM", actual_old, new, merge=True, force=True)
			out["merged"].append(f"{actual_old} => {new}")

	# 3. Disable unused non-FBR UOMs
	used = _used_uoms()
	non_fbr = frappe.get_all("UOM",
		filters={"custom_is_fbr_uom": 0, "enabled": 1}, pluck="name")
	for name in non_fbr:
		if name in used:
			out["skipped"].append(name)  # commercial/pack UOM in use — keep
			continue
		frappe.db.set_value("UOM", name, "enabled", 0, update_modified=False)
		out["disabled"] += 1

	if verbose:
		print("renamed:", out["renamed"])
		print("merged:", out["merged"])
		print("disabled:", out["disabled"], "| kept-in-use non-FBR:", out["skipped"])
	return out


def reparse_rates(verbose=True):
	"""Re-run the rate_desc parser across all FBR Rate rows (after parser changes)."""
	from pakistan_tax.fbr.sync import parse_rate_desc
	updated = 0
	for row in frappe.get_all("FBR Rate", fields=["name", "rate_desc"]):
		parsed = parse_rate_desc(row.rate_desc)
		fixed_uom = parsed.pop("fixed_uom", None)
		parsed["fixed_uom"] = fixed_uom if fixed_uom and frappe.db.exists("UOM", fixed_uom) else None
		frappe.db.set_value("FBR Rate", row.name, parsed, update_modified=False)
		updated += 1
	if verbose:
		print("reparsed:", updated)
	return updated
