// Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Agent Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Sync App Seeds"), () => {
			frappe.call({
				method: "huf.ai.app_seeding.seeder.seed_all_apps",
				freeze: true,
				freeze_message: __("Syncing App Seeds..."),
				callback: function(r) {
					if (r.message && r.message.status === "success") {
						frappe.show_alert({
							message: __(r.message.message),
							indicator: "green"
						});
					}
				}
			});
		}, __("Actions"));
	},
});
