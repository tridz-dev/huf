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

// ─── Rows, summary, import/export (Tables redesign) ───

export type TableRecordFilter = [string, string, unknown];

export interface TableRecordsParams {
	fields?: string[];
	filters?: TableRecordFilter[];
	search?: string;
	limit?: number;
	start?: number;
	orderBy?: { field: string; order: 'asc' | 'desc' };
}

/** `total` is undefined when talking to an older backend. */
export interface TableRecordsResult {
	items: Record<string, unknown>[];
	hasMore: boolean;
	total?: number;
}

export interface BulkInsertResult {
	inserted: string[];
	errors: Array<{ index: number; message: string }>;
}

export interface TableSummaryAgent {
	agent: string;
	agent_name: string;
	actions: TableAgentAction[];
}

export interface TableSummary {
	name: string;
	table_name: string;
	description: string;
	table_group?: string;
	icon: string;
	field_count: number;
	record_count: number;
	modified: string;
	agents: TableSummaryAgent[];
}

export interface TableDependencies {
	record_count: number;
	agents: Array<{ agent: string; agent_name: string }>;
	flows: Array<{ name: string; title: string }>;
}

export interface TableToolParam {
	name: string;
	type: string;
	required: boolean;
	description: string;
	options?: string;
}

export interface TableToolSignature {
	tools: Array<{
		action: TableAgentAction | string;
		tool_name: string;
		description: string;
		params: TableToolParam[];
	}>;
}

export interface TableAgentActivityItem {
	agent: string;
	tool: string;
	status: string;
	timestamp: string;
}

export type ImportMode = 'insert' | 'update' | 'replace';

export interface ImportPreviewColumn {
	header: string;
	detected_type: string;
	mapped_field: string | null;
	issues: number;
}

export interface ImportRowIssue {
	row: number;
	message: string;
}

export interface ImportPreview {
	columns: ImportPreviewColumn[];
	sample_rows: unknown[][];
	total_rows: number;
	valid_rows: number;
	invalid_rows: ImportRowIssue[];
}

export interface RunImportParams {
	mapping: Record<string, string | null>;
	mode: ImportMode;
	keyField?: string;
	/** Must be true for mode 'replace'. */
	confirmReplace?: boolean;
}

export interface RunImportResult {
	inserted: number;
	updated: number;
	rejected: number;
	rejected_rows: ImportRowIssue[];
	rejected_csv: string;
	note?: string;
	skipped?: number;
	skipped_rows?: ImportRowIssue[];
}

export interface QueuedImport {
	queued: true;
	job_id: string;
}

export interface ImportJobStatus {
	status: 'queued' | 'running' | 'done' | 'failed';
	progress?: number;
	result?: RunImportResult;
	error?: string;
}

export interface ExportRowsParams {
	filters?: TableRecordFilter[];
	fields?: string[];
	names?: string[];
}

export interface ExportRowsResult {
	filename: string;
	content: string;
	count: number;
}
