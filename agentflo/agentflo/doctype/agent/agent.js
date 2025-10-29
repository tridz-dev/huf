// Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
// For license information, please see license.txt


frappe.ui.form.on("Agent", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Go to Agent Console"), () => {
				frappe.route_options = {
					agent_name: frm.doc.name,
					provider: frm.doc.provider,
					model: frm.doc.model,
				};
				frappe.set_route("Form", "Agent Console");
			});

			if (frm.doc.allow_chat) {
				frm.add_custom_button(__("Go to Agent Chat"), () => {
					frappe.new_doc("Agent Chat", {
						agent: frm.doc.name,
					});
				});
			}
		}
	},
		provider(frm) {
			frm.set_value("model", "");
	
			if (frm.doc.provider) {
				frm.set_query("model", () => ({
					filters: { provider: frm.doc.provider }
				}));
			} else {
				frm.set_query("model", () => ({}));
			}
		},
	
	
});
