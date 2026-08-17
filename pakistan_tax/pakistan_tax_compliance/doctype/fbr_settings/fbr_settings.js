// Copyright (c) 2026, SpotLedger
// For license information, please see license.txt

frappe.ui.form.on('FBR Settings', {
	refresh: function(frm) {
		frm.add_custom_button(__('Sync Provinces'), function() {
			let env = frm.doc.environment;
			let token = env === "Sandbox" ? frm.doc.sandbox_token : frm.doc.production_token;
			if (!token) {
				frappe.msgprint(__('Please enter the {0} API token first.', [env]));
				return;
			}
			frappe.call({
				method: "pakistan_tax.pakistan_tax_compliance.doctype.fbr_settings.fbr_settings.sync_provinces",
				args: {
					env: env,
					token: token
				},
				freeze: true,
				freeze_message: __("Syncing Provinces from FBR..."),
				callback: function(r) {
					if (!r.exc) {
						frappe.msgprint(__('Provinces synced successfully.'));
					}
				}
			});
		});
	}
});
