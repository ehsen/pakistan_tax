# Copyright (c) 2026, SpotLedger
"""Tax Ledger Entry posting for import-stage taxes (Landed Cost Voucher).

Deliberately independent of importmanager: this reacts to "Landed Cost
Voucher", a core ERPNext doctype, and reads its custom fields defensively
(doc.get()/row.get(), never attribute access) so a site with pakistan_tax
but no import-management app installed just no-ops here instead of
erroring. The specific field names below (custom_landed_cost_voucher_type,
custom_stamnt, custom_ast, custom_it, custom_base_assessed_value,
custom_import_document) match importmanager's schema, the only producer of
this data today.

Import-stage Custom Duty/ACD/Cess are intentionally excluded — those are a
Customs Act stock-costing matter, not a Sales Tax Act or Income Tax
Ordinance position, so they have no place in this subledger.

Mirrors pakistan_tax.tax_ledger.posting.on_invoice_submit: one aggregate
row per voucher, not per line — HS-code-level detail is answered by a
report joining Landed Cost Item.item_code -> Item.customs_tariff_number
(see report "Import Input Tax by HS Code"), the same pattern already used
for Annex-C, not by adding line-level rows to Tax Ledger Entry.
"""

import frappe
from frappe.utils import flt

from pakistan_tax.tax_ledger.posting import _insert

IMPORT_ADVANCE_TAX_SECTION = "148"


def on_lcv_submit(doc, method=None):
	if doc.get("custom_landed_cost_voucher_type") != "Import":
		return

	items = doc.get("items") or []
	st_total = sum(flt(row.get("custom_stamnt")) + flt(row.get("custom_ast")) for row in items)
	it_total = sum(flt(row.get("custom_it")) for row in items)
	if not st_total and not it_total:
		return

	# Customs-assessed value is always populated (calculate_assessed_value()
	# runs unconditionally, even under Manual Data Entry) so it's the one
	# reliable stored base to report as "taxable amount" here. It is the
	# customs assessed value, not the true ST-inclusive-of-duty base (that
	# intermediate figure is never persisted) — informational only, nothing
	# downstream computes off it.
	taxable_amount = sum(flt(row.get("custom_base_assessed_value")) for row in items)

	import_doc_name = doc.get("custom_import_document")
	gd_no = supplier = None
	if import_doc_name:
		gd_no, supplier = frappe.db.get_value(
			"ImportDoc", import_doc_name, ["gd_no", "supplier"]
		) or (None, None)

	common = {
		"posting_date": doc.posting_date,
		"company": doc.company,
		"party_type": "Supplier" if supplier else None,
		"party": supplier,
		"party_ntn": frappe.db.get_value("Supplier", supplier, "tax_id") if supplier else None,
		"voucher_type": doc.doctype,
		"voucher_no": doc.name,
		"gd_no": gd_no,
		"tax_authority": "FBR",
	}

	if st_total:
		_insert(tax_type="Input ST", status="Claimed",
			taxable_amount=taxable_amount, tax_amount=st_total, **common)

	if it_total:
		_insert(tax_type="WHT Receivable", status="Deposited",
			section=IMPORT_ADVANCE_TAX_SECTION,
			taxable_amount=taxable_amount, tax_amount=it_total, **common)
