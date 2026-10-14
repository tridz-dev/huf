frappe.ui.form.on("Gateway", {
    refresh: function(frm) {
        let apps = frappe.boot.installed_apps || [];
        let has_whatsapp = apps.includes("frappe_whatsapp");

        frm.dashboard.clear_headline();
        if (frm.doc.provider === "WhatsApp" && !has_whatsapp) {
            frm.dashboard.set_headline(
                __("The frappe_whatsapp app is not installed. This gateway will call the Meta Cloud API directly; install frappe_whatsapp (https://github.com/shridarpatil/frappe_whatsapp) to use a WhatsApp Account, templates and message history."),
                "orange"
            );
        }
    },
    provider: function(frm) {
        frm.trigger("refresh");
    }
});
