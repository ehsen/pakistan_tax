# Copyright (c) 2026, SpotLedger
"""One-time backfill: Item Tax Template generation was never wired into
daily_sync() or install, so sites that synced FBR rates before this fix
accumulated open FBR Transaction Type Rate associations with zero generated
templates. Run the same generation every company with an enabled FBR
Settings would get from now on via fbr.sync.daily_sync."""

import frappe


def execute():
	from pakistan_tax.tax_config.template_generator import (
		generate_item_tax_templates, update_transaction_type_defaults)

	companies = frappe.get_all("FBR Settings", filters={"is_enabled": 1}, pluck="company")
	for company in companies:
		try:
			generate_item_tax_templates(company)
			update_transaction_type_defaults(company)
		except Exception:
			frappe.log_error(title="FBR Item Tax Template bootstrap failed",
				message=f"company={company}\n{frappe.get_traceback()}")
