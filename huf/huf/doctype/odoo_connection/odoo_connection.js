frappe.ui.form.on("Odoo Connection", {
    refresh(frm) {
        frm.add_custom_button(__("Test Connection"), () => {
            frm.call("test_connection").then(r => {
                frm.reload_doc();
                if (r.message && r.message.success) {
                    frappe.show_alert({
                        message: __("Connection successful! Odoo version: {0}", [r.message.version]),
                        indicator: "green"
                    });
                } else {
                    frappe.msgprint({
                        title: __("Connection Failed"),
                        message: r.message?.error || __("Unknown error"),
                        indicator: "red"
                    });
                }
            });
        });

        if (frm.doc.connection_status === "Connected") {
            frm.add_custom_button(__("Discover Schema"), () => {
                frappe.call({
                    method: "huf.ai.odoo.schema.discover_schema",
                    args: { connection_name: frm.doc.name },
                    callback(r) {
                        if (r.message) {
                            frappe.show_alert({
                                message: __("Schema discovery started in background."),
                                indicator: "blue"
                            });
                        }
                    }
                });
            }, __("Action"));

            frm.add_custom_button(__("View Cached Schema"), () => {
                frappe.set_route("List", "Odoo Schema Cache", {
                    connection: frm.doc.name
                });
            }, __("Action"));
        }
    }
});
