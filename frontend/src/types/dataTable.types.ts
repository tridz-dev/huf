/**
 * A field definition for the table builder
 */
export interface DataTableFieldDef {
	fieldname: string;
	fieldtype: DataTableFieldType;
	label: string;
	reqd?: 0 | 1;
	unique?: 0 | 1;
	read_only?: 0 | 1;
	hidden?: 0 | 1;
	default?: string;
	options?: string;
	description?: string;
	in_list_view?: 0 | 1;
	non_negative?: 0 | 1;
	idx?: number;
}

/**
 * Allowed field types for Huf data tables
 */
export type DataTableFieldType =
	| 'Data'
	| 'Small Text'
	| 'Text'
	| 'Long Text'
	| 'Int'
	| 'Float'
	| 'Currency'
	| 'Percent'
	| 'Check'
	| 'Date'
	| 'Datetime'
	| 'Time'
	| 'Duration'
	| 'Select'
	| 'Link'
	| 'Rating'
	| 'Color'
	| 'Phone'
	| 'Attach'
	| 'Attach Image'
	| 'Tab Break'
	| 'Section Break'
	| 'Column Break';

/**
 * Layout-only field types (no DB column)
 */
export type LayoutFieldType = 'Tab Break' | 'Section Break' | 'Column Break';

/**
 * Huf Data Table registry record (from Frappe)
 */
export interface HufDataTable {
	name: string;
	table_name: string;
	doctype_name: string;
	description: string;
	icon: string;
	field_count: number;
	record_count: number;
	is_active: 0 | 1;
	autoname_method: 'Autoincrement' | 'Hash' | 'By Field';
	title_field_name: string;
	table_group?: string;
	creation: string;
	modified: string;
}

/**
 * Full table schema (registry + field definitions)
 */
export interface DataTableSchema {
	name: string;
	table_name: string;
	doctype_name: string;
	description: string;
	icon: string;
	autoname_method: string;
	title_field_name: string;
	table_group?: string;
	fields: DataTableFieldDef[];
}

/**
 * Plain user-facing actions for the "Add to agent" flow.
 * The backend owns the mapping to Agent Tool Function `types`
 * (huf/huf/doctype/huf_data_table/api.py TABLE_ACTION_MAP).
 */
export type TableAgentAction = 'view' | 'create' | 'edit' | 'delete';

/**
 * One agent's access to a Huf data table, as returned by
 * get_table_agent_access / set_table_agent_access.
 */
export interface TableAgentAccess {
	agent: string;
	agent_name: string;
	actions: TableAgentAction[];
	tools: string[];
}

/**
 * Field type metadata for the field type selector
 */
export interface FieldTypeInfo {
	type: DataTableFieldType;
	label: string;
	description: string;
	icon: string;
	category: string;
	hasOptions: boolean;
	supportsUnique: boolean;
	supportsNonNegative: boolean;
}
