// Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Remote Agent Connection", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Test Connection"), function () {
				frm.events.test_connection(frm);
			}, __("Actions"));

			frm.add_custom_button(__("Refresh Manifest"), function () {
				frm.events.refresh_manifest(frm);
			}, __("Actions"));
		}
	},

	test_connection(frm) {
		frappe.call({
			method: "test_connection_cmd",
			doc: frm.doc,
			args: {
				connection_name: frm.doc.name
			},
			freeze: true,
			freeze_message: __("Testing remote agent connection..."),
			callback: function (r) {
				if (r.message && r.message.status === "healthy") {
					frappe.msgprint({
						title: __("Connection Successful"),
						message: __("Successfully connected to remote agent."),
						indicator: "green"
					});
				} else {
					frappe.msgprint({
						title: __("Connection Failed"),
						message: r.message ? r.message.message : __("Unknown error"),
						indicator: "red"
					});
				}
				frm.reload_doc();
			}
		});
	},

	refresh_manifest(frm) {
		frappe.call({
			method: "refresh_manifest_cmd",
			doc: frm.doc,
			args: {
				connection_name: frm.doc.name
			},
			freeze: true,
			freeze_message: __("Refreshing remote agent manifest..."),
			callback: function (r) {
				if (!r.exc) {
					frappe.show_alert({
						message: __("Manifest refreshed successfully"),
						indicator: "green"
					});
					frm.reload_doc();
				}
			}
		});
	}
});
