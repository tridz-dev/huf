// Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("Agent Orchestration", {
    refresh: function (frm) {
        // Requirement 3: Recreate Plan Button
        if (frm.doc.status !== "Completed" && !frm.is_new()) {
            frm.add_custom_button(__("Recreate Plan"), function () {
                frappe.call({
                    method: "huf.ai.orchestration.orchestrator.recreate_orchestration_plan",
                    args: { orch_name: frm.doc.name },
                    freeze: true,
                    callback: function (r) {
                        if (r.message) {
                            frm.reload_doc();
                            frappe.msgprint(__("Plan recreated from Agent instructions."));
                        }
                    }
                });
            });
        }

        // Feature: Stop Orchestration
        if (["Planned", "Running", "Paused"].includes(frm.doc.status) && !frm.is_new()) {
            frm.add_custom_button(__("Stop Execution"), function () {
                frappe.confirm(__("Are you sure you want to stop this orchestration?"), function () {
                    frappe.call({
                        method: "huf.ai.orchestration.orchestrator.stop_orchestration",
                        args: { orch_name: frm.doc.name },
                        freeze: true,
                        callback: function (r) {
                            frm.reload_doc();
                        }
                    });
                });
            }).addClass("btn-danger");
        }
    }
});