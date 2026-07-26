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

        // OAuth: show Connect/Disconnect and status badge
        if (frm.doc.auth_type === "oauth" && !frm.is_new()) {
            frm.events.render_oauth_status(frm);
        }
    },

    render_oauth_status(frm) {
        const status = frm.doc.oauth_status || "Not Connected";
        const colours = { "Connected": "green", "Token Expired": "orange", "Not Connected": "red" };
        const colour = colours[status] || "red";
        frm.get_field("oauth_status").$wrapper
            .find(".control-value")
            .html(`<span class="indicator-pill ${colour}">${status}</span>`);
    },

    oauth_connect_button(frm) {
        // URL-first entry point.  The backend decides whether to use manually
        // configured OAuth endpoints or to run discovery + dynamic client
        // registration, so no client-side validation is performed here.
        frappe.call({
            method: "huf.ai.mcp_oauth.resolve_and_start_oauth_flow",
            args: { server_name: frm.doc.name },
            freeze: true,
            freeze_message: __("Discovering OAuth settings…"),
            callback(r) {
                if (r.message && r.message.auth_url) {
                    const win = window.open(r.message.auth_url, "_blank", "width=600,height=700");
                    // Poll for the window to close, then refresh form
                    const poll = setInterval(() => {
                        if (!win || win.closed) {
                            clearInterval(poll);
                            frm.reload_doc();
                        }
                    }, 1000);
                } else {
                    frappe.msgprint({ title: __("Error"), message: r.message?.error || __("Could not start OAuth flow."), indicator: "red" });
                }
            }
        });
    },

    oauth_disconnect_button(frm) {
        frappe.confirm(__("Disconnect this MCP Server from OAuth? Tokens will be deleted."), () => {
            frappe.call({
                method: "huf.ai.mcp_oauth.disconnect_oauth",
                args: { server_name: frm.doc.name },
                freeze: true,
                callback(r) {
                    if (r.message?.success) {
                        frappe.show_alert({ message: __("Disconnected"), indicator: "green" });
                        frm.reload_doc();
                    } else {
                        frappe.msgprint({ title: __("Error"), message: r.message?.error, indicator: "red" });
                    }
                }
            });
        });
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
