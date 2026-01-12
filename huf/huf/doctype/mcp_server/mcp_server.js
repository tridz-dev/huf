// Copyright (c) 2025, Tridz Technologies Pvt Ltd
// For license information, please see license.txt

frappe.ui.form.on("MCP Server", {
    refresh(frm) {
        // Add sync tools button handler
        if (!frm.is_new()) {
            frm.add_custom_button(__("Sync Tools"), function () {
                frm.events.sync_tools(frm);
            }, __("Actions"));

            // Add test connection button
            frm.add_custom_button(__("Test Connection"), function () {
                frappe.call({
                    method: "huf.ai.mcp_client.test_mcp_connection",
                    args: {
                        server_name: frm.doc.name
                    },
                    freeze: true,
                    freeze_message: __("Testing connection..."),
                    callback: function (r) {
                        if (r.message && r.message.success) {
                            frappe.msgprint({
                                title: __("Connection Successful"),
                                message: __("Successfully connected to MCP server"),
                                indicator: "green"
                            });
                        } else {
                            frappe.msgprint({
                                title: __("Connection Failed"),
                                message: r.message ? r.message.error : __("Unknown error"),
                                indicator: "red"
                            });
                        }
                    }
                });
            }, __("Actions"));
        }
    },

    sync_tools_button(frm) {
        frm.events.sync_tools(frm);
    },

    sync_tools(frm) {
        frm.call({
            method: "sync_tools",
            doc: frm.doc,
            freeze: true,
            freeze_message: __("Syncing tools from MCP server..."),
            callback: function (r) {
                if (r.message && r.message.success) {
                    frm.reload_doc();
                }
            }
        });
    },



    auth_type(frm) {
        // Set default header name based on auth type
        if (frm.doc.auth_type === "bearer_token") {
            frm.set_value("auth_header_name", "Authorization");
        } else if (frm.doc.auth_type === "api_key") {
            frm.set_value("auth_header_name", "X-API-Key");
        }
    }
});
