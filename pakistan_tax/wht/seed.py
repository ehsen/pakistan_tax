# Copyright (c) 2026, SpotLedger
"""Seeds WHT Section + WHT Rate from bundled reference data
(wht/data/wht_reference_data.json), parsed from FBR's Tax Payment Nature Code
list.

Idempotent: existing section_code / (section, condition) records are left
untouched (so users can freely edit sections/rates after install without
losing changes on the next migrate). Company-specific fields (payable/
receivable accounts) are never touched here — those are set per company via
the tax_config bootstrap or manually, same as everywhere else in this app.

Data quality notes (kept honest rather than papered over):
- Rows where the source description gives no percentage figure at all
  (salary sections, rent, vehicle/property fees, license fees, etc.) are
  seeded with not_a_flat_rate=1 and rate 0 — they need manual configuration,
  never a fabricated number.
- Rows with 3+ percentage figures in one description (e.g. the 236G
  fertilizer combined IT+ST rate) are flagged the same way — a flat
  filer/non-filer pair can't honestly represent them.
- The source spreadsheet's "Relevant Codes" cross-reference to statutory
  exemption clauses was corrupted by Excel's numeric precision loss and is
  not imported.
"""

import json
import os

import frappe

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "wht_reference_data.json")


def _load():
	with open(DATA_FILE) as f:
		return json.load(f)


@frappe.whitelist()
def seed_wht_reference_data():
	frappe.only_for("System Manager")
	return _seed()


def _seed():
	"""Internal entry point — called directly from after_install (no
	permission check needed there; the whitelisted wrapper above guards the
	on-demand re-run path)."""
	data = _load()
	created_sections = created_rates = skipped = 0

	for row in data["sections"]:
		if frappe.db.exists("WHT Section", row["section_code"]):
			continue
		frappe.get_doc({
			"doctype": "WHT Section",
			"section_code": row["section_code"],
			"section_description": row["section_description"],
		}).insert(ignore_permissions=True)
		created_sections += 1

	for row in data["rates"]:
		if not frappe.db.exists("WHT Section", row["section"]):
			continue  # shouldn't happen, but never fail the whole seed on one bad row
		existing = frappe.db.exists("WHT Rate", {
			"section": row["section"], "condition": row["condition"]})
		if existing:
			skipped += 1
			continue
		frappe.get_doc({
			"doctype": "WHT Rate",
			"section": row["section"],
			"condition": row["condition"],
			"filer_rate": row["filer_rate"],
			"non_filer_rate": row["non_filer_rate"],
			"not_a_flat_rate": row["not_a_flat_rate"],
			"nature_code": row["nature_code"],
			"reference_note": row["reference_note"],
		}).insert(ignore_permissions=True)
		created_rates += 1

	return {
		"sections_created": created_sections,
		"rates_created": created_rates,
		"rates_already_present": skipped,
		"source_note": data["source"],
	}
