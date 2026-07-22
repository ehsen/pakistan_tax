# Copyright (c) 2026, SpotLedger
"""Install-time setup: custom fields owned by pakistan_tax.

All custom fields this app needs live here (created via after_install /
after_migrate) so nothing exists only in a site database.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "Pakistan Tax Compliance"

CUSTOM_FIELDS = {
	"UOM": [
		{
			"fieldname": "custom_is_fbr_uom",
			"fieldtype": "Check",
			"label": "Is FBR UOM",
			"insert_after": "enabled",
			"read_only": 1,
			"module": MODULE,
		},
		{
			"fieldname": "custom_fbr_uom_id",
			"fieldtype": "Int",
			"label": "FBR UOM ID",
			"insert_after": "custom_is_fbr_uom",
			"read_only": 1,
			"module": MODULE,
		},
	],
}


def after_install():
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


def after_migrate():
	# Idempotent — keeps fields present on every migrate
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
