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

						const results = r.message.results || [];
						const skipped = results.flatMap((res) =>
							(res.skipped_records || []).map((rec) => ({
								app: rec.app || res.app,
								file: rec.file,
								record: rec.record,
								missing: (rec.missing_refs || []).join(", ") || rec.error,
							}))
						);

						if (skipped.length) {
							const rows = skipped
								.map(
									(rec) =>
										`<tr><td>${frappe.utils.escape_html(rec.app)}</td>` +
										`<td>${frappe.utils.escape_html(rec.file)}</td>` +
										`<td>${frappe.utils.escape_html(rec.record)}</td>` +
										`<td>${frappe.utils.escape_html(rec.missing)}</td></tr>`
								)
								.join("");
							const html =
								`<p>${__("The following seeds were skipped because they reference missing documents:")}</p>` +
								`<table class="table table-bordered table-hover table-striped">` +
								`<thead><tr>` +
								`<th>${__("App")}</th><th>${__("File")}</th><th>${__("Record")}</th><th>${__("Missing References")}</th>` +
								`</tr></thead><tbody>${rows}</tbody></table>`;
							frappe.msgprint({
								message: html,
								title: __("Skipped Seeds"),
								indicator: "orange",
							});
						}
					}
				}
			});
		}, __("Actions"));
	},
});
