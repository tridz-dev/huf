// Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on('Agent Tool Function', {
	refresh(frm) {
		if (frm.doc.reference_doctype) {
			_update_field_options(frm);
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
			const skip = ['name','owner','creation','modified','modified_by','docstatus'];
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

function _map_fieldtype_to_param(df) {
	if (!df) return 'string';
	const ft = df.fieldtype;

	if (['Int', 'Integer', 'Small Int', 'Long'].includes(ft)) return 'integer';
	if (['Float', 'Currency', 'Percent', 'Duration'].includes(ft)) return 'number';
	if (ft === 'Check') return 'boolean';
	return 'string';
}

function _add_mandatory_fields(frm) {
	if (!frm.doc.reference_doctype) return;

	frappe.model.with_doctype(frm.doc.reference_doctype, () => {
		const meta = frappe.get_meta(frm.doc.reference_doctype);

		const system_ignore = ['name','owner','creation','modified','modified_by','docstatus'];
		meta.fields.forEach(df => {
			if (df.reqd && !system_ignore.includes(df.fieldname)) {
				const exists = (frm.doc.parameters || []).some(p => p.fieldname === df.fieldname);
				if (!exists) {
					const row = frm.add_child('parameters');
					row.label = df.label || df.fieldname;
					row.fieldname = df.fieldname;
					row.type = _map_fieldtype_to_param(df);
					row.required = 1;

					if (df.fieldtype === 'Table') {
						row.child_table_name = df.fieldname;
					}
				}
			}
		});

		frm.refresh_field('parameters');
	});
}
