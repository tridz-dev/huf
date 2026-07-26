// Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('Agent Tool Function', {
	refresh(frm) {
		if (frm.doc.reference_doctype) {
			_update_field_options(frm);
			frm.add_custom_button(__('Select Fields from DocType'), () => {
				_show_field_selector_dialog(frm);
			});
		}
		if (frm.doc.types === "Custom Function" && frm.doc.function_path) {
			frm.add_custom_button(__('Fetch Params from Code'), function () {
				frappe.call({
					doc: frm.doc,
					method: 'fetch_parameters_from_code',
					freeze: true,
					callback: function (r) {
						if (!r.exc) {
							frm.reload_doc();
							frappe.msgprint(__("Parameters updated from function signature."));
						}
					}
				});
			});
		}
	},

	reference_doctype(frm) {
		_update_field_options(frm);

		if (frm.doc.types && ['Create Document', 'Create Multiple Documents'].includes(frm.doc.types)) {
			_add_mandatory_fields(frm);
		}
	},

	types(frm) {
		if (frm.doc.reference_doctype && ['Create Document', 'Create Multiple Documents'].includes(frm.doc.types)) {
			_add_mandatory_fields(frm);
		}
	}
});

function _update_field_options(frm) {
	if (!frm.doc.reference_doctype) return;

	frappe.model.with_doctype(frm.doc.reference_doctype, () => {
		const meta = frappe.get_meta(frm.doc.reference_doctype);
		const options = [];
		const map = {};

		meta.fields.forEach(f => {
			const skip = ['name', 'owner', 'creation', 'modified', 'modified_by', 'docstatus'];
			if (skip.includes(f.fieldname)) return;

			const label = f.label || f.fieldname;
			options.push(label);
			map[label] = f.fieldname;
		});

		frm._agent_field_map = frm._agent_field_map || {};
		frm._agent_field_map[frm.doc.reference_doctype] = { map: map, meta: meta };

		frm.fields_dict['parameters'].grid.refresh();
	});
}


function _show_field_selector_dialog(frm) {
	if (!frm.doc.reference_doctype) {
		frappe.msgprint(__("Please select a Reference DocType first."));
		return;
	}

	frappe.model.with_doctype(frm.doc.reference_doctype, () => {
		let meta = frappe.get_meta(frm.doc.reference_doctype);

		// Identify Child Tables
		let child_tables = meta.fields.filter(df => df.fieldtype === 'Table' && df.options);
		let child_doctypes = child_tables.map(df => df.options);

		// Helper to recursively load child doctypes
		let load_child_doctypes = (index, callback) => {
			if (index >= child_doctypes.length) {
				callback();
				return;
			}
			frappe.model.with_doctype(child_doctypes[index], () => {
				load_child_doctypes(index + 1, callback);
			});
		};

		load_child_doctypes(0, () => {
			// All Metas Loaded. Build Options.
			let current_fields = (frm.doc.parameters || []).map(p => {
				return p.child_table_name ? `${p.child_table_name}:${p.fieldname}` : p.fieldname;
			});

			let fields_to_show = [];

			// 1. Parent Fields
			meta.fields.forEach(df => {
				if (['Section Break', 'Column Break', 'Tab Break', 'HTML', 'Button', 'Image', 'Fold', 'Table'].includes(df.fieldtype) || df.hidden) return;

				if (!current_fields.includes(df.fieldname)) {
					fields_to_show.push({
						label: `${df.label} (${df.fieldname})`,
						value: df.fieldname,
						checked: 0
					});
				}
			});

			// 2. Child Table Fields
			child_tables.forEach(table_df => {
				let child_meta = frappe.get_meta(table_df.options);
				if (!child_meta) return;

				child_meta.fields.forEach(cdf => {
					if (['Section Break', 'Column Break', 'Tab Break', 'HTML', 'Button', 'Image', 'Fold'].includes(cdf.fieldtype) || cdf.hidden) return;

					let item_key = `${table_df.fieldname}:${cdf.fieldname}`;
					if (!current_fields.includes(item_key)) {
						fields_to_show.push({
							label: `${table_df.label} > ${cdf.label} (${cdf.fieldname})`,
							value: item_key,
							checked: 0
						});
					}
				});
			});

			if (fields_to_show.length === 0) {
				frappe.msgprint(__("All available fields are already added."));
				return;
			}

			let d = new frappe.ui.Dialog({
				title: __('Select Fields to Add'),
				fields: [
					{
						label: 'Fields',
						fieldtype: 'MultiCheck',
						options: fields_to_show,
						fieldname: 'selected_fields',
						columns: 2
					}
				],
				primary_action_label: __('Add Fields'),
				primary_action: (values) => {
					let selected_values = values.selected_fields; // Array of values

					selected_values.forEach(val => {
						// Check if it's a child field (contains colon)
						if (val.includes(':')) {
							// Child Table Field
							let [table_fieldname, child_fieldname] = val.split(':');
							let table_df = meta.fields.find(f => f.fieldname === table_fieldname);
							if (table_df) {
								let child_meta = frappe.get_meta(table_df.options);
								let df = child_meta.fields.find(f => f.fieldname === child_fieldname);

								if (df) {
									let row = frm.add_child('parameters');
									row.label = df.label || df.fieldname;
									row.fieldname = df.fieldname; // Item code
									row.child_table_name = table_fieldname; // items
									row.type = _map_fieldtype_to_param(df);
									row.required = 0;
									if (df.fieldtype === 'Select') row.options = df.options;
								}
							}

						} else {
							// Parent Field
							let df = meta.fields.find(f => f.fieldname === val);
							if (df) {
								let row = frm.add_child('parameters');
								row.label = df.label || df.fieldname;
								row.fieldname = df.fieldname;
								row.type = _map_fieldtype_to_param(df);
								row.required = 0;
								if (df.fieldtype === 'Select') row.options = df.options;
							}
						}
					});

					frm.refresh_field('parameters');
					d.hide();
					frappe.show_alert({ message: __('Fields Added'), indicator: 'green' });
				}
			});

			d.show();
		});
	});
}

function _map_fieldtype_to_param(df) {
	if (!df) return 'string';
	const ft = df.fieldtype;

	if (['Int', 'Integer', 'Small Int', 'Long'].includes(ft)) return 'integer';
	if (['Float', 'Currency', 'Percent', 'Duration'].includes(ft)) return 'number';
	if (ft === 'Check') return 'boolean';
	if (['Table'].includes(ft)) return 'array';
	return 'string';
}

function _add_mandatory_fields(frm) {
	if (!frm.doc.reference_doctype) return;

	frappe.model.with_doctype(frm.doc.reference_doctype, () => {
		const meta = frappe.get_meta(frm.doc.reference_doctype);

		const system_ignore = ['name', 'owner', 'creation', 'modified', 'modified_by', 'docstatus'];
		meta.fields.forEach(df => {
			if (df.reqd && !system_ignore.includes(df.fieldname) && df.fieldtype !== 'Table') {
				const exists = (frm.doc.parameters || []).some(p => p.fieldname === df.fieldname);
				if (!exists) {
					const row = frm.add_child('parameters');
					row.label = df.label || df.fieldname;
					row.fieldname = df.fieldname;
					row.type = _map_fieldtype_to_param(df);
					row.required = 1;

					if (df.fieldtype === 'Select') {
						row.options = df.options;
					}
				}
			}
		});

		frm.refresh_field('parameters');
	});
}
