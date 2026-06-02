frappe.ui.form.on('Memory Record', {
    refresh(frm) {
        if (frm.doc.__islocal) {
            return;
        }

        if (frm.doc.status === 'Draft') {
            frm.add_custom_button(__('Activate'), () => {
                frm.set_value('status', 'Active');
                frm.save();
            });
        }

        if (frm.doc.promote_to_knowledge && frm.doc.knowledge_source && frm.doc.status === 'Active') {
            frm.add_custom_button(__('Queue Knowledge Projection'), () => {
                frappe.call({
                    method: 'huf.huf.doctype.memory_record.memory_record.queue_memory_knowledge_projection',
                    args: { memory_record: frm.doc.name },
                    callback: () => frm.reload_doc()
                });
            }, __('Knowledge'));
        }

        if (frm.doc.knowledge_input) {
            frm.add_custom_button(__('Open Knowledge Input'), () => {
                frappe.set_route('Form', 'Knowledge Input', frm.doc.knowledge_input);
            }, __('Knowledge'));

            frm.add_custom_button(__('Remove Knowledge Projection'), () => {
                frappe.confirm(__('Remove the Knowledge Input projection for this memory record?'), () => {
                    frappe.call({
                        method: 'huf.huf.doctype.memory_record.memory_record.remove_memory_knowledge_projection',
                        args: { memory_record: frm.doc.name },
                        callback: () => frm.reload_doc()
                    });
                });
            }, __('Knowledge'));
        }
    }
});
