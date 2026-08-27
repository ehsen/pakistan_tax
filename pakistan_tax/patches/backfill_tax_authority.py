# Copyright (c) 2026, SpotLedger
"""One-time backfill for the Tax Authority dimension (plan §3.10 in
PAKISTAN_TAX_APP_PLAN.md). Every existing row in this app predates the
concept and is, by construction, FBR — stamp it explicitly rather than
leaving it null, so nothing silently reports as "no authority"."""

import frappe


def execute():
	# post_model_sync patches run before hooks.after_migrate, so the
	# pk_tax_authority custom fields don't exist yet at this point on a
	# fresh migrate — create them here too (idempotent) before backfilling.
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
	from pakistan_tax.setup.install import CUSTOM_FIELDS
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)

	from pakistan_tax.tax_config.authority_seed import _seed
	_seed()

	frappe.db.sql("""
		update `tabItem Tax Template`
		set pk_tax_authority = 'FBR'
		where coalesce(pk_tax_authority, '') = ''
	""")
	frappe.db.sql("""
		update `tabWHT Section`
		set tax_authority = 'FBR'
		where coalesce(tax_authority, '') = ''
	""")
	for doctype in ("Sales Invoice", "Purchase Invoice"):
		frappe.db.sql(f"""
			update `tab{doctype}`
			set pk_tax_authority = 'FBR'
			where docstatus = 1 and coalesce(pk_tax_authority, '') = ''
		""")
	frappe.db.sql("""
		update `tabTax Ledger Entry`
		set tax_authority = 'FBR'
		where coalesce(tax_authority, '') = '' and coalesce(section, '') = ''
	""")
	# WHT-derived TLE rows (section set) get FBR via their now-backfilled section
	frappe.db.sql("""
		update `tabTax Ledger Entry` tle
		join `tabWHT Section` s on s.name = tle.section
		set tle.tax_authority = s.tax_authority
		where coalesce(tle.tax_authority, '') = ''
	""")
