// Copyright (c) 2024, Tridz and contributors
// For license information, please see license.txt

frappe.ui.form.on('Flow Run', {
    refresh: function(frm) {
        if (frm.doc.status === 'Waiting Approval') {
            frm.add_custom_button('Approve', () => {
                frappe.prompt([
                    {
                        fieldname: 'comment',
                        label: 'Comment (Optional)',
                        fieldtype: 'Small Text'
                    }
                ], (values) => {
                    frappe.call({
                        method: 'huf.ai.flow_engine.approve_flow_run',
                        args: {
                            flow_run_name: frm.doc.name,
                            decision: 'approved',
                            comment: values.comment || ''
                        },
                        callback: function(r) {
                            if (!r.exc) {
                                frappe.show_alert({message: 'Flow Approved and Resumed', indicator: 'green'});
                                frm.reload_doc();
                            }
                        }
                    });
                }, 'Approve Flow', 'Approve');
            }).addClass('btn-success');

            frm.add_custom_button('Reject', () => {
                frappe.prompt([
                    {
                        fieldname: 'comment',
                        label: 'Reason for Rejection',
                        fieldtype: 'Small Text',
                        reqd: 1
                    }
                ], (values) => {
                    frappe.call({
                        method: 'huf.ai.flow_engine.approve_flow_run',
                        args: {
                            flow_run_name: frm.doc.name,
                            decision: 'rejected',
                            comment: values.comment
                        },
                        callback: function(r) {
                            if (!r.exc) {
                                frappe.show_alert({message: 'Flow Rejected and Resumed', indicator: 'red'});
                                frm.reload_doc();
                            }
                        }
                    });
                }, 'Reject Flow', 'Reject');
            }).addClass('btn-danger');
        }
    }
});
