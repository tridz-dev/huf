// Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors

frappe.ui.form.on("Agent Console", {
	refresh(frm) {
        frm.add_custom_button("Run Agent", function() {
            console.log("Run Agent button clicked");
            frappe.call({
                method: "agentflo.ai.agent_integration.run_agent_sync",
                args: {
                    agent_name: frm.doc.agent_name,
                    prompt: frm.doc.prompt
                },
                callback: function(r) {
                    frm.doc.response = r.message.response;
                    frm.refresh_field("response");
                    console.log("Agent run completed", r.message.response);
                }
            });
        },);
    
	},
});
