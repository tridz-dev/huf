frappe.ui.form.on("Agent Console", {
    refresh(frm) {
        frm.disable_save();

        frm.set_value("agent_name", "");
        frm.set_value("prompt", "");
        frm.set_value("response", "");

        frm.page.set_primary_action(__("Run Agent"), ($btn) => {
            $btn.text(__("Running..."));

            frappe.call({
                method: "agentflo.ai.agent_integration.run_agent_sync",
                args: {
                    agent_name: frm.doc.agent_name,
                    prompt: frm.doc.prompt,
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
