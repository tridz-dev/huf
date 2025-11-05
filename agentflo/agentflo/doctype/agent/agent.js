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
			
			// Export/Import buttons
			if (frm.doc.is_standard && frappe.boot.developer_mode) {
				frm.add_custom_button(__("Export Agent"), () => {
					export_agent(frm);
				});
			}
			
			// Always show import button for System Managers
			if (frappe.user.has_role("System Manager")) {
				frm.add_custom_button(__("Import Agent"), () => {
					import_agent(frm);
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

function export_agent(frm) {
	frappe.call({
		method: "agentflo.agentflo.doctype.agent.agent.export_agent",
		args: {},
		freeze: true,
		freeze_message: __("Exporting agent..."),
		callback: function(r) {
			if (r.message) {
				// Download as JSON file
				const agent_data = r.message;
				const filename = `${frm.doc.agent_name.replace(/\s+/g, "_")}_export_${frappe.datetime.get_datetime_as_string().replace(/[:\s]/g, "_")}.json`;
				
				const blob = new Blob([JSON.stringify(agent_data, null, 2)], {
					type: "application/json"
				});
				const url = URL.createObjectURL(blob);
				const a = document.createElement("a");
				a.href = url;
				a.download = filename;
				document.body.appendChild(a);
				a.click();
				document.body.removeChild(a);
				URL.revokeObjectURL(url);
				
				frappe.show_alert({
					message: __("Agent exported successfully"),
					indicator: "green"
				});
			}
		},
		error: function(r) {
			frappe.show_alert({
				message: __("Failed to export agent: {0}", [r.message || "Unknown error"]),
				indicator: "red"
			});
		}
	});
}

function import_agent(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Import Agent"),
		fields: [
			{
				label: __("Import Mode"),
				fieldname: "import_mode",
				fieldtype: "Select",
				options: "\nmerge\nskip\noverwrite",
				default: "merge",
				description: __("merge: Update if exists, skip: Skip if exists, overwrite: Replace if exists")
			},
			{
				label: __("Agent JSON File"),
				fieldname: "file",
				fieldtype: "Attach",
				reqd: 1
			}
		],
		primary_action_label: __("Import"),
		primary_action: function(values) {
			dialog.hide();
			
			// Get file and read content
			frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "File",
					name: values.file
				},
				callback: function(r) {
					if (r.message) {
						const file_doc = r.message;
						// Use file_url for import
						const file_path = file_doc.file_url || file_doc.file_name;
						
						frappe.call({
							method: "agentflo.agentflo.doctype.agent.agent.import_agent_from_file",
							args: {
								file_path: file_path,
								import_mode: values.import_mode
							},
							freeze: true,
							freeze_message: __("Importing agent..."),
							callback: function(r2) {
								if (r2.message) {
									frappe.show_alert({
										message: __("Agent '{0}' imported successfully", [r2.message]),
										indicator: "green"
									});
									// Reload list if on list view, otherwise reload form
									if (frm.doctype) {
										frappe.set_route("List", "Agent");
									} else {
										frm.reload_doc();
									}
								}
							},
							error: function(r2) {
								frappe.show_alert({
									message: __("Failed to import agent: {0}", [r2.message || "Unknown error"]),
									indicator: "red"
								});
							}
						});
					}
				}
			});
		}
	});
	
	dialog.show();
}
