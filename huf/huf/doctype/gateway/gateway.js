frappe.ui.form.on("Gateway", {
    refresh: function(frm) {
        let apps = frappe.boot.installed_apps || [];
        let has_whatsapp = apps.includes("frappe_whatsapp");

        if (frm.doc.provider === "WhatsApp" && !has_whatsapp) {
            frm.dashboard.set_headline(__("whatsapp_gateway_app missing: Please install the 'frappe_whatsapp' app (https://github.com/shridarpatil/frappe_whatsapp) to use the WhatsApp gateway."), "red");
            frm.disable_save();
            // Gray out fields
            frm.set_df_property('provider', 'read_only', 0); // Keep provider editable to change it back
            frm.set_df_property('integration_settings', 'read_only', 1);
            frm.set_df_property('is_enabled', 'read_only', 1);
        } else {
            frm.dashboard.clear_headline();
            frm.enable_save();
            frm.set_df_property('integration_settings', 'read_only', 0);
            frm.set_df_property('is_enabled', 'read_only', 0);
        }
    },
    provider: function(frm) {
        frm.trigger("refresh");
    }
});
