# Copyright (c) 2026, SpotLedger
"""Bootinfo — data the client needs synchronously, before any user
interaction, so there's no async-fetch race to lose. Used by
public/js/tax_row_direction.js: an async frappe.call to fetch this per
company loses the race against a user adding the very first item on a
freshly loaded form (add_taxes_from_item_tax_template can fire before the
fetch resolves), letting the wrong-direction tax row through. Baking it
into boot removes the race entirely."""

import frappe


def boot_session(bootinfo):
	rows = frappe.get_all("FBR Settings", fields=["company",
		"account_sales_tax", "account_input_sales_tax"])
	bootinfo.pakistan_tax_direction_accounts = {
		row.company: {
			"output": [a for a in (row.account_sales_tax,) if a],
			"input": [a for a in (row.account_input_sales_tax,) if a],
		}
		for row in rows
	}
