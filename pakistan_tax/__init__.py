__version__ = "0.0.1"


def _patch_process_item_selection():
	"""erpnext.utilities.transaction_base.TransactionBase.add_taxes_from_item_template
	has the same gap as the client-side add_taxes_from_item_tax_template it
	mirrors: it appends a bare {charge_type, account_head, rate} tax row with
	no category ("Consider Tax or Charge for") / add_deduct_tax ("Add or
	Deduct") / description — all mandatory — which blocks save with
	"Missing Fields". Confirmed live in browser testing: with
	frappe.boot.sysdefaults.use_legacy_js_reactivity off (the v16 default),
	item selection runs through this server-side path via the whitelisted
	process_item_selection RPC (see transaction.js), which never goes
	through validate/before_validate — our doc_events hooks never see it, so
	it has to be patched at the source, not caught downstream."""
	import frappe
	from erpnext.utilities.transaction_base import TransactionBase

	original = TransactionBase.process_item_selection

	@frappe.whitelist()
	def patched(self, item_idx):
		original(self, item_idx)
		if self.get("pk_is_tax_invoice"):
			from pakistan_tax.transactions.resolution import _reconcile_ad_hoc_tax_rows
			_reconcile_ad_hoc_tax_rows(self)
			self.calculate_taxes_and_totals()

	TransactionBase.process_item_selection = patched


_patch_process_item_selection()
