// Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
// For license information, please see license.txt

function check_caching_support(frm) {
	const provider = frm.doc.provider;
	const model = frm.doc.model;

	if (!frm.doc.enable_prompt_caching || !provider || !model) return;

	frappe.call({
		method: "huf.huf.doctype.agent.agent.get_cacheable_models",
		args: { provider, model },
		callback(r) {
			if (!r || !r.message) return;
			const { supported, alternatives } = r.message;

			if (!supported) {
				let msg;
				if (alternatives && alternatives.length) {
					const shown = alternatives.slice(0, 5);
					msg = __(
						"<b>Warning:</b> The selected model does not support prompt caching.<br>" +
						"Supported models from this provider: <b>{0}</b>.",
						[shown.join("</b>, <b>")]
					);
				} else {
					msg = __(
						"<b>Warning:</b> The selected model does not support prompt caching. " +
						"No other models from this provider currently support caching either."
					);
				}

				frappe.show_alert({
					message: msg,
					indicator: "orange",
				}, 10);
			}
		},
		error() {
		},
	});
}



frappe.ui.form.on("Agent", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Go to Agent Console"), () => {
				frappe.route_options = {
					agent_name: frm.doc.name,
					provider: frm.doc.provider,
					model: frm.doc.model,
				};
				frappe.set_route("Form", "Agent Console");
			});

			if (frm.doc.allow_chat) {
				frm.add_custom_button(__("Go to Agent Chat"), () => {
					frappe.new_doc("Agent Chat", {
						agent: frm.doc.name,
					});
				});
			}
		}
	},
	provider(frm) {
		frm.set_value("model", "");

		if (frm.doc.provider) {
			frm.set_query("model", () => ({
				filters: { provider: frm.doc.provider }
			}));
		} else {
			frm.set_query("model", () => ({}));
		}
	},
	onload(frm) {
		// Filter advanced model pickers by modality/task capability
		frm.set_query("image_generation_model", () => ({
			query: "huf.huf.doctype.ai_model.ai_model.get_models_by_modality",
			filters: { modality: "Image" },
		}));

		frm.set_query("tts_model", () => ({
			query: "huf.huf.doctype.ai_model.ai_model.get_models_by_modality",
			filters: { modality: "Text-to-Speech" },
		}));

		frm.set_query("stt_model", () => ({
			query: "huf.huf.doctype.ai_model.ai_model.get_models_by_modality",
			filters: { modality: "Transcription" },
		}));
	},
	enable_prompt_caching(frm) {
		check_caching_support(frm);
	},

	model(frm) {
		if (frm.doc.enable_prompt_caching) {
			check_caching_support(frm);
		}
	},
});

frappe.ui.form.on("Agent MCP Server", {
	mcp_server(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.mcp_server) {
			frappe.db.get_doc("MCP Server", row.mcp_server).then(doc => {
				let count = 0;
				if (doc.tools) {
					count = doc.tools.length;
				}
				frappe.model.set_value(cdt, cdn, "tool_count", count);
			});
		} else {
			frappe.model.set_value(cdt, cdn, "tool_count", 0);
		}
	}
});
