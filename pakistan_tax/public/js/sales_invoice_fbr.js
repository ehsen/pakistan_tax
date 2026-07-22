// Copyright (c) 2026, SpotLedger
// FBR Digital Invoicing buttons on Sales Invoice

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || !frm.doc.pk_is_tax_invoice) return;

		if (frm.doc.pk_fbr_posting_status !== "Posted") {
			frm.add_custom_button(__("Validate with FBR"), () => {
				frappe.call({
					method: "pakistan_tax.transactions.fbr_posting.validate_with_fbr",
					args: { invoice_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Validating with FBR..."),
					callback(r) {
						const res = r.message || {};
						if (res.success) {
							frappe.msgprint({
								title: __("FBR Validation"),
								message: __("Invoice data is VALID per FBR"),
								indicator: "green",
							});
						} else {
							frappe.msgprint({
								title: __("FBR Validation Failed"),
								message: frappe.utils.escape_html(
									res.error_text || JSON.stringify(res.response)
								).replace(/\n/g, "<br>"),
								indicator: "red",
							});
						}
					},
				});
			}, __("FBR"));

			frm.add_custom_button(__("Post to FBR"), () => {
				frappe.confirm(
					__("Post this invoice to FBR Digital Invoicing?"),
					() => {
						frappe.call({
							method: "pakistan_tax.transactions.fbr_posting.post_to_fbr",
							args: { invoice_name: frm.doc.name },
							freeze: true,
							freeze_message: __("Posting to FBR..."),
							callback(r) {
								const res = r.message || {};
								if (res.success) {
									frappe.msgprint({
										title: __("Posted to FBR"),
										message: __("FBR Invoice Number: {0}", [
											res.fbr_invoice_number,
										]),
										indicator: "green",
									});
									frm.reload_doc();
								} else {
									frappe.msgprint({
										title: __("FBR Posting Failed"),
										message: frappe.utils.escape_html(
											res.error_text || ""
										).replace(/\n/g, "<br>"),
										indicator: "red",
									});
									frm.reload_doc();
								}
							},
						});
					}
				);
			}, __("FBR"));
		}

		if (frm.doc.pk_fbr_invoice_number) {
			frm.dashboard.set_headline(
				__("FBR Invoice: {0}", [frm.doc.pk_fbr_invoice_number])
			);
		}
	},
});
