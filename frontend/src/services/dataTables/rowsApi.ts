import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type {
	BulkInsertResult,
	ExportRowsParams,
	ExportRowsResult,
	ImportJobStatus,
	ImportPreview,
	QueuedImport,
	RunImportParams,
	RunImportResult,
	TableAgentActivityItem,
	TableDependencies,
	TableSummary,
	TableToolSignature,
} from '@/types/dataTable.types';

const P = 'huf.huf.doctype.huf_data_table';

export async function bulkInsertRows(
	doctypeName: string,
	rows: Record<string, unknown>[]
): Promise<BulkInsertResult> {
	try {
		const r = await call.post(`${P}.rows.bulk_insert_rows`, {
			doctype_name: doctypeName,
			rows: JSON.stringify(rows),
		});
		return r.message as BulkInsertResult;
	} catch (error) {
		handleFrappeError(error, 'Error adding rows');
	}
}

export async function bulkUpdateRows(
	doctypeName: string,
	names: string[],
	values: Record<string, unknown>
): Promise<{ updated: number }> {
	try {
		const r = await call.post(`${P}.rows.bulk_update_rows`, {
			doctype_name: doctypeName,
			names: JSON.stringify(names),
			values: JSON.stringify(values),
		});
		return r.message as { updated: number };
	} catch (error) {
		handleFrappeError(error, 'Error updating rows');
	}
}

export async function bulkDeleteRows(
	doctypeName: string,
	names: string[]
): Promise<{ deleted: number }> {
	try {
		const r = await call.post(`${P}.rows.bulk_delete_rows`, {
			doctype_name: doctypeName,
			names: JSON.stringify(names),
		});
		return r.message as { deleted: number };
	} catch (error) {
		handleFrappeError(error, 'Error deleting rows');
	}
}

export async function restoreRows(
	doctypeName: string,
	names: string[]
): Promise<{ restored: number }> {
	try {
		const r = await call.post(`${P}.rows.restore_rows`, {
			doctype_name: doctypeName,
			names: JSON.stringify(names),
		});
		return r.message as { restored: number };
	} catch (error) {
		handleFrappeError(error, 'Error restoring rows');
	}
}

export async function listTablesSummary(): Promise<TableSummary[]> {
	try {
		const r = await call.get(`${P}.rows.list_tables_summary`);
		return (r.message ?? []) as TableSummary[];
	} catch (error) {
		handleFrappeError(error, 'Error fetching tables');
	}
}

export async function getTableDependencies(tableId: string): Promise<TableDependencies> {
	try {
		const r = await call.get(`${P}.rows.get_table_dependencies`, { table_id: tableId });
		return r.message as TableDependencies;
	} catch (error) {
		handleFrappeError(error, 'Error fetching table dependencies');
	}
}

export async function getTableToolSignature(tableId: string): Promise<TableToolSignature> {
	try {
		const r = await call.get(`${P}.rows.get_table_tool_signature`, { table_id: tableId });
		return r.message as TableToolSignature;
	} catch (error) {
		handleFrappeError(error, 'Error fetching tool signature');
	}
}

export async function getTableAgentActivity(
	tableId: string,
	limit = 20
): Promise<TableAgentActivityItem[]> {
	try {
		const r = await call.get(`${P}.rows.get_table_agent_activity`, { table_id: tableId, limit });
		return (r.message ?? []) as TableAgentActivityItem[];
	} catch (error) {
		handleFrappeError(error, 'Error fetching agent activity');
	}
}

export async function previewImport(tableId: string, fileUrl: string): Promise<ImportPreview> {
	try {
		const r = await call.post(`${P}.import_export.preview_import`, {
			table_id: tableId,
			file_url: fileUrl,
		});
		return r.message as ImportPreview;
	} catch (error) {
		handleFrappeError(error, 'Error previewing import');
	}
}

export function isQueuedImport(r: RunImportResult | QueuedImport): r is QueuedImport {
	return (r as QueuedImport).queued === true;
}

export async function getImportJobStatus(jobId: string): Promise<ImportJobStatus> {
	try {
		const r = await call.get(`${P}.import_export.get_import_job_status`, { job_id: jobId });
		return r.message as ImportJobStatus;
	} catch (error) {
		handleFrappeError(error, 'Error checking import status');
	}
}

export async function runImport(
	tableId: string,
	fileUrl: string,
	params: RunImportParams
): Promise<RunImportResult | QueuedImport> {
	try {
		const r = await call.post(`${P}.import_export.run_import`, {
			table_id: tableId,
			file_url: fileUrl,
			mapping: JSON.stringify(params.mapping),
			mode: params.mode,
			key_field: params.keyField,
			confirm_replace: params.confirmReplace ? 1 : undefined,
		});
		return r.message as RunImportResult | QueuedImport;
	} catch (error) {
		handleFrappeError(error, 'Error importing rows');
	}
}

export async function exportRows(
	tableId: string,
	params?: ExportRowsParams
): Promise<ExportRowsResult> {
	try {
		const r = await call.get(`${P}.import_export.export_rows`, {
			table_id: tableId,
			filters: params?.filters ? JSON.stringify(params.filters) : undefined,
			fields: params?.fields ? JSON.stringify(params.fields) : undefined,
			names: params?.names ? JSON.stringify(params.names) : undefined,
		});
		return r.message as ExportRowsResult;
	} catch (error) {
		handleFrappeError(error, 'Error exporting rows');
	}
}
