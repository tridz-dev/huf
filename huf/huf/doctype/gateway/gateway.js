frappe.ui.form.on("Gateway", {
    refresh: function(frm) {
        frm.dashboard.clear_headline();
        if (frm.doc.provider !== "WhatsApp") {
            return;
        }
        // Ask the server whether frappe_whatsapp's DocTypes exist on this site.
        // frappe.boot.installed_apps is not a reliable signal here, so only show the
        // banner when the connector check explicitly reports it unavailable.
        frappe.call({
            method: "huf.ai.whatsapp.management.get_setup_status",
            callback: function(r) {
                let msg = (r && r.message) || {};
                if (msg.success !== false && msg.connector_available === false) {
                    frm.dashboard.set_headline(
                        __("The frappe_whatsapp app is not installed. This gateway will call the Meta Cloud API directly; install frappe_whatsapp (https://github.com/shridarpatil/frappe_whatsapp) to use a WhatsApp Account, templates and message history."),
                        "orange"
                    );
                }
            }
        });
    },
    provider: function(frm) {
        frm.trigger("refresh");
    }
});
