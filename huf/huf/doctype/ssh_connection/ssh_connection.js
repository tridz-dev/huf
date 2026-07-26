frappe.ui.form.on("SSH Connection", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Test Connection"), async () => {
			await runConnectionAction(frm, "huf.huf.doctype.ssh_connection.ssh_connection.test_ssh_connection", {
				connection_name: frm.doc.name,
			}, __("Testing SSH connection..."));
		}, __("Actions"));

		frm.add_custom_button(__("Enroll Host Key"), async () => {
			frappe.confirm(
				__("Enroll or replace the pinned host key using the server's current fingerprint?"),
				async () => {
					await runConnectionAction(frm, "huf.huf.doctype.ssh_connection.ssh_connection.enroll_host_key", {
						connection_name: frm.doc.name,
					}, __("Enrolling SSH host key..."));
				}
			);
		}, __("Actions"));
	},
});

async function runConnectionAction(frm, method, args, freezeMessage) {
	try {
		const r = await frappe.call({
			method,
			args,
			freeze: true,
			freeze_message: freezeMessage,
		});
		const result = r.message || {};
		if (result.success) {
			frappe.show_alert({
				message: result.fingerprint
					? __("Success: {0}", [result.fingerprint])
					: __("SSH action completed successfully"),
				indicator: "green",
			});
			await frm.reload_doc();
			return;
		}

		frappe.msgprint({
			title: __("SSH Action Failed"),
			message: result.error || __("Unknown error"),
			indicator: "red",
		});
	} catch (error) {
		frappe.msgprint({
			title: __("SSH Action Failed"),
			message: error?.message || __("Unknown error"),
			indicator: "red",
		});
	}
}
