// Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('Agent Trigger', {
    refresh: function(frm) {
        if (frm.doc.reference_doctype) {
            frm.trigger('set_prompt_field_options');
        }
    },

    reference_doctype: function(frm) {
        frm.set_value('prompt_field', '');
        frm.trigger('set_prompt_field_options');
    },

    set_prompt_field_options: function(frm) {
        if (!frm.doc.reference_doctype) return;

        frappe.model.with_doctype(frm.doc.reference_doctype, function() {
            let meta = frappe.get_meta(frm.doc.reference_doctype);

            let options = meta.fields
                .filter(df => !['Section Break', 'Column Break', 'Tab Break', 'Table'].includes(df.fieldtype))
                .map(df => df.fieldname);

            let standard_fields = ['name', 'owner', 'creation', 'modified', 'docstatus'];
            options = [...standard_fields, ...options];

            frm.set_df_property('prompt_field', 'options', options);
        });
    }
});

frappe.ui.form.on('Agent Trigger Attachment', {
    source_type: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.source_type === "Child Table Field" && frm.doc.reference_doctype) {
            frappe.model.with_doctype(frm.doc.reference_doctype, function() {
                let parent_meta = frappe.get_meta(frm.doc.reference_doctype);

                let tables = parent_meta.fields
                    .filter(df => df.fieldtype === "Table")
                    .map(df => df.fieldname);
                frm.fields_dict["file_attachments"].grid.update_docfield_property(
                    "child_table", "options", tables
                );
                frm.refresh_field("file_attachments");
            });
        }
    }
})