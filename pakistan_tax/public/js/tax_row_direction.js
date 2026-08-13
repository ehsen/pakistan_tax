// Copyright (c) 2026, SpotLedger
// Stops "Add Taxes from Item Tax Template" (Accounts Settings) from ever
// pulling the wrong-direction account onto a Sales/Purchase Invoice. One
// Item Tax Template is shared across both — it legitimately carries both
// the output account (Sales) and the input account (Purchase) for the same
// rate — but the native client-side helper adds every account in the map
// regardless of which document it's on, and never fills in the mandatory
// fields on what it adds. Filtering here means the wrong row never appears
// at all, instead of appearing and needing a save round-trip to get
// cleaned up server-side (see resolution.py::_reconcile_ad_hoc_tax_rows,
// the backstop for anything this doesn't catch — e.g. API-created docs).
//
// The direction map comes from frappe.boot (pakistan_tax/boot.py), not an
// async frappe.call: a per-company fetch loses the race against a user
// adding the very first item on a freshly loaded form — this function can
// fire before that fetch resolves, letting the wrong row through anyway.
// Boot data is present before the form is even interactive, so there is no
// race to lose.

const PK_TAX_SCOPED_DOCTYPES = { "Purchase Invoice": "input", "Sales Invoice": "output" };

const native_add_taxes_from_item_tax_template =
	erpnext.taxes_and_totals.prototype.add_taxes_from_item_tax_template;

erpnext.taxes_and_totals.prototype.add_taxes_from_item_tax_template = function (item_tax_map) {
	const doctype = this.frm && this.frm.doc && this.frm.doc.doctype;
	const own_direction = PK_TAX_SCOPED_DOCTYPES[doctype];
	if (!own_direction || !item_tax_map) {
		return native_add_taxes_from_item_tax_template.call(this, item_tax_map);
	}

	const wrong_direction = own_direction === "input" ? "output" : "input";
	const company = this.frm.doc.company;
	const direction_accounts = (frappe.boot.pakistan_tax_direction_accounts || {})[company];
	let map = typeof item_tax_map === "string" ? JSON.parse(item_tax_map) : item_tax_map;

	if (direction_accounts) {
		const blocked = direction_accounts[wrong_direction] || [];
		map = Object.fromEntries(
			Object.entries(map).filter(([account]) => !blocked.includes(account))
		);
	}

	const before_count = (this.frm.doc.taxes || []).length;
	const result = native_add_taxes_from_item_tax_template.call(this, map);

	(this.frm.doc.taxes || []).slice(before_count).forEach((row) => {
		if (!row.set_by_item_tax_template) return;
		if (frappe.meta.has_field(row.doctype, "category") && !row.category) {
			row.category = "Total";
		}
		if (frappe.meta.has_field(row.doctype, "add_deduct_tax") && !row.add_deduct_tax) {
			row.add_deduct_tax = "Add";
		}
		if (!row.description) {
			row.description = row.account_head;
		}
	});

	return result;
};
