frappe.ui.form.on('Agent Prompt', {
    refresh: function (frm) {
        // Only show versioning options for saved, user-managed prompts
        if (!frm.is_new() && !frm.doc.is_system && frm.doc.is_latest) {

            frm.add_custom_button(__('Create New Version'), function () {
                frappe.prompt([
                    {
                        label: 'Title (Optional)',
                        fieldname: 'title',
                        fieldtype: 'Data',
                        default: frm.doc.title,
                        description: 'Leave as is to keep the same title.'
                    },
                    {
                        label: 'Description (Optional)',
                        fieldname: 'description',
                        fieldtype: 'Small Text',
                        default: frm.doc.description
                    }
                ], function (values) {
                    frappe.call({
                        method: 'ivendnext_ai_agents.ai.prompt_api.create_new_version',
                        args: {
                            prompt_name: frm.doc.name,
                            prompt_body: frm.doc.prompt_body,
                            title: values.title,
                            description: values.description
                        },
                        freeze: true,
                        freeze_message: __('Creating new version...'),
                        callback: function (r) {
                            if (r.message && r.message.name) {
                                frappe.show_alert({
                                    message: __('Created version {0}', [r.message.version]),
                                    indicator: 'green'
                                });
                                // Route to the new version
                                frappe.set_route('Form', 'Agent Prompt', r.message.name);
                            }
                        }
                    });
                }, __('Create New Version'), __('Create'));
            }, __('Actions'));

            frm.add_custom_button(__('Fork Prompt'), function () {
                frappe.prompt([
                    {
                        label: 'Title for Fork',
                        fieldname: 'title',
                        fieldtype: 'Data',
                        default: frm.doc.title + ' (Fork)',
                        reqd: 1
                    }
                ], function (values) {
                    frappe.call({
                        method: 'ivendnext_ai_agents.ai.prompt_api.fork_prompt',
                        args: {
                            prompt_name: frm.doc.name,
                            title: values.title
                        },
                        freeze: true,
                        freeze_message: __('Forking prompt...'),
                        callback: function (r) {
                            if (r.message && r.message.name) {
                                frappe.show_alert({
                                    message: __('Prompt forked successfully'),
                                    indicator: 'green'
                                });
                                // Route to the new fork
                                frappe.set_route('Form', 'Agent Prompt', r.message.name);
                            }
                        }
                    });
                }, __('Fork Prompt'), __('Fork'));
            }, __('Actions'));
        }
    }
});
