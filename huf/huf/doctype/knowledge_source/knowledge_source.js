// Copyright (c) 2025, Huf and contributors
// For license information, please see license.txt

frappe.ui.form.on("Knowledge Source", {
	refresh(frm) {
		// Add Rebuild Index button
		if (!frm.is_new() && frm.doc.status !== "Indexing" && frm.doc.status !== "Rebuilding") {
			frm.add_custom_button(__("Rebuild Index"), function() {
				frappe.confirm(
					__("This will clear the existing index and rebuild it from all inputs. Continue?"),
					function() {
						frappe.call({
							method: "huf.huf.doctype.knowledge_source.knowledge_source.rebuild_index",
							args: { knowledge_source: frm.doc.name },
							callback: function(r) {
								if (r.message) {
									frappe.show_alert({
										message: r.message.message,
										indicator: "green"
									});
									frm.reload_doc();
								}
							}
						});
					}
				);
			}, __("Actions"));
		}
		
		// Add Test Search button
		if (!frm.is_new() && frm.doc.status === "Ready") {
			frm.add_custom_button(__("Test Search"), function() {
				show_test_search_dialog(frm);
			}, __("Actions"));
		}
		
		// Status indicator
		if (frm.doc.status === "Ready") {
			frm.dashboard.set_headline_alert(
				__("Index ready with {0} chunks", [frm.doc.total_chunks || 0]),
				"green"
			);
		} else if (frm.doc.status === "Error") {
			frm.dashboard.set_headline_alert(
				__("Error: {0}", [frm.doc.error_message || "Unknown error"]),
				"red"
			);
		} else if (frm.doc.status === "Indexing" || frm.doc.status === "Rebuilding") {
			frm.dashboard.set_headline_alert(__("Indexing in progress..."), "blue");
		}
	},
	
	knowledge_type(frm) {
		// Phase 1: Only sqlite_fts is supported
		if (frm.doc.knowledge_type && frm.doc.knowledge_type !== "sqlite_fts") {
			frappe.msgprint(__("Only SQLite FTS is supported in Phase 1"));
			frm.set_value("knowledge_type", "sqlite_fts");
		}
	}
});

function show_test_search_dialog(frm) {
	let d = new frappe.ui.Dialog({
		title: __("Test Search"),
		fields: [
			{
				label: __("Search Query"),
				fieldname: "query",
				fieldtype: "Small Text",
				reqd: 1
			},
			{
				label: __("Top K Results"),
				fieldname: "top_k",
				fieldtype: "Int",
				default: 5
			},
			{
				label: __("Results"),
				fieldname: "results_html",
				fieldtype: "HTML"
			}
		],
		primary_action_label: __("Search"),
		primary_action(values) {
			frappe.call({
				method: "huf.huf.doctype.knowledge_source.knowledge_source.test_search",
				args: {
					knowledge_source: frm.doc.name,
					query: values.query,
					top_k: values.top_k || 5
				},
				callback: function(r) {
					if (r.message) {
						let html = render_search_results(r.message);
						d.fields_dict.results_html.$wrapper.html(html);
					}
				}
			});
		}
	});
	d.show();
}

function render_search_results(results) {
	if (!results || results.length === 0) {
		return `<p class="text-muted">${__("No results found")}</p>`;
	}
	
	let html = '<div class="search-results">';
	results.forEach((r, i) => {
		html += `
			<div class="result-item mb-3 p-3 border rounded">
				<div class="d-flex justify-content-between mb-2">
					<strong>${r.title || 'Chunk ' + (i + 1)}</strong>
					<span class="text-muted">Score: ${r.score?.toFixed(3) || 'N/A'}</span>
				</div>
				<p class="mb-0 small">${frappe.utils.escape_html(r.text?.substring(0, 300))}...</p>
			</div>
		`;
	});
	html += '</div>';
	return html;
}
