// Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('AI Provider', {
    refresh: function(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__('Provider Settings'), function() {
                frappe.call({
                    method: 'huf.huf.doctype.ai_provider.ai_provider.get_provider_settings',
                    args: { provider_name: frm.doc.name }, // Use frm.doc.name for accuracy
                    callback: function(r) {
                        if (r.message && r.message.length > 0) {
                            frappe.set_route('Form', r.message[0], r.message[0]);
                        } else {
                            frappe.msgprint(`Please create a Single DocType named <b>${frm.doc.name} Settings</b> to configure this provider.`);
                        }
                    }
                });
            });
        }
    }
});