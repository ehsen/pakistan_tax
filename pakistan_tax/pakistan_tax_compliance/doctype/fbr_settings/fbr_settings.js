// Copyright (c) 2026, SpotLedger
// For license information, please see license.txt

frappe.ui.form.on('FBR Settings', {
	refresh: function(frm) {
		frm.add_custom_button(__('Fetch Tax Updates from FBR'), function() {
			if (frm.is_new()) {
				frappe.msgprint(__('Please save FBR Settings before fetching tax updates.'));
				return;
			}

			frappe.call({
				method: "pakistan_tax.pakistan_tax_compliance.doctype.fbr_settings.fbr_settings.fetch_tax_updates",
				args: { company: frm.doc.name },
				callback: function(r) {
					if (!r.exc) {
						frappe.show_alert({
							message: __('Fetching tax updates from FBR in the background — provinces first, then the rest. You will be notified here when it completes.'),
							indicator: 'blue'
						}, 7);
					}
				}
			});
		});
	}
});
