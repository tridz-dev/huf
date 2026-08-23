/**
 * Types for AI-generated artifacts and web previews
 */

export type ArtifactType =
	| 'code'
	| 'document'
	| 'html'
	| 'svg'
	| 'mermaid'
	| 'react-component'
	| 'markdown'
	| 'jsx'
	| 'chart'
	| 'video'
	| 'frappe-list'
	| 'frappe-form'
	| 'frappe-report';

export interface ParsedArtifact {
	id: string;
	type: ArtifactType;
	title?: string;
	language?: string;
	content: string;
}

export interface ParsedWebPreview {
	url: string;
	title?: string;
}

export interface ParsedJSXPreview {
	jsx: string;
	title?: string;
	isStreaming?: boolean;
}

export interface ArtifactParseResult {
	text: string;
	artifacts: ParsedArtifact[];
}

export interface WebPreviewParseResult {
	text: string;
	previews: ParsedWebPreview[];
}

export interface JSXPreviewParseResult {
	text: string;
	previews: ParsedJSXPreview[];
}

/**
 * Types for the frappe-list / frappe-form / frappe-report artifact payload
 * emitted by huf/ai/tools/frappe_generic.py::handle_render_frappe_view.
 *
 * These mirror the JSON shape exactly as produced by
 * `_describe_field`/`handle_get_doctype_meta` in that module - see it before
 * changing these, since the backend is the source of truth for field keys.
 */

/** One DocField as described by `_describe_field` in frappe_generic.py. */
export interface FrappeFieldMeta {
	fieldname: string;
	label: string | null;
	fieldtype: string;
	options: string | null;
	reqd: boolean;
	read_only: boolean;
	depends_on: string | null;
	fetch_from: string | null;
	/** Present only when fieldtype === 'Select'. */
	select_options?: string[];
	/** Present only when fieldtype === 'Link' - the target doctype name. */
	link_doctype?: string;
	/** Present only when fieldtype === 'Table'. */
	child_doctype?: string;
	child_fields?: FrappeFieldMeta[];
	child_fields_error?: string;
}

/** The `meta` object nested in every frappe-* artifact payload - the raw
 * return value of handle_get_doctype_meta, not re-wrapped. */
export interface FrappeDoctypeMeta {
	success: boolean;
	doctype: string;
	is_submittable: boolean;
	title_field: string | null;
	fields: FrappeFieldMeta[];
}

export type FrappeViewMode = 'list' | 'form' | 'report';

/**
 * Envelope shape common to frappe-list, frappe-form, and frappe-report
 * artifacts. `data` is a record array for list/report mode and a single
 * record object for form mode - narrow on `mode` before using it.
 *
 * `limit_start`/`limit_page_length` are present for list/report mode only
 * (mirrors handle_list_records's raw JSON); absent for form mode.
 */
export interface FrappeViewPayload {
	doctype: string;
	mode: FrappeViewMode;
	meta: FrappeDoctypeMeta;
	filters?: Record<string, unknown> | unknown[] | null;
	fields?: string[] | null;
	data: Record<string, unknown>[] | Record<string, unknown>;
	total_count?: number;
	limit_start?: number;
	limit_page_length?: number;
}
