// Copyright (c) 2025, Huf and contributors
// For license information, please see license.txt

frappe.listview_settings["Knowledge Source"] = {
	add_fields: ["status", "total_chunks", "disabled"],
	
	get_indicator(doc) {
		if (doc.disabled) {
			return [__("Disabled"), "gray", "disabled,=,1"];
		}
		
		const status_map = {
			"Ready": ["Ready", "green"],
			"Pending": ["Pending", "orange"],
			"Indexing": ["Indexing", "blue"],
			"Rebuilding": ["Rebuilding", "blue"],
			"Error": ["Error", "red"],
		};
		
		const [label, color] = status_map[doc.status] || ["Unknown", "gray"];
		return [__(label), color, `status,=,${doc.status}`];
	},
	
	formatters: {
		total_chunks(value) {
			return value ? frappe.utils.format_number(value) : "0";
		}
	}
};
