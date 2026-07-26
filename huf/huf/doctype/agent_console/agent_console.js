frappe.ui.form.on("Agent Console", {
    refresh(frm) {
        frm.disable_save();

        if (frappe.route_options) {
            frm.set_value("agent_name", frappe.route_options.agent_name);
            frm.set_value("provider", frappe.route_options.provider);
            frm.set_value("model", frappe.route_options.model);
            frappe.route_options = null;
            frm.set_value("prompt", "");
            frm.set_value("response", "");
        } else {
            frm.set_value("agent_name", "");
            frm.set_value("provider", "");
            frm.set_value("prompt", "");
            frm.set_value("response", "");
        }


        frm.page.set_primary_action(__("Run Agent"), ($btn) => {
            $btn.text(__("Running..."));

            frappe.call({
                method: "huf.ai.agent_integration.run_agent_sync",
                args: {
                    agent_name: frm.doc.agent_name,
                    prompt: frm.doc.prompt,
                    provider:frm.doc.provider,
                    model:frm.doc.model
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value("response", r.message.response || "");
                    }
                    $btn.text(__("Run Agent"));
                },
                error: function() {
                    frappe.msgprint(__("Something went wrong while running the agent."));
                    $btn.text(__("Run Agent"));
                }
            });
        });
    },
});
