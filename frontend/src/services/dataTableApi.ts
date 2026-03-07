import { db, call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type {
	DataTableFieldDef,
	DataTableSchema,
	HufDataTable,
	PaginatedDataTablesResponse,
	GetDataTablesParams,
} from '@/types/dataTable.types';

/**
 * Fetch all data tables with pagination and search
 */
export async function getDataTables(
	params?: GetDataTablesParams
): Promise<PaginatedDataTablesResponse> {
	try {
		const result = await call.get('huf.huf.doctype.huf_data_table.api.get_data_tables', {
			search: params?.search || '',
			limit: params?.limit || 20,
			start: params?.start || 0,
		});
		return result.message as PaginatedDataTablesResponse;
	} catch (error) {
		handleFrappeError(error, 'Error fetching data tables');
	}
}

/**
 * Get full table schema (fields + metadata)
 */
export async function getTableSchema(name: string): Promise<DataTableSchema> {
	try {
		const result = await call.get('huf.huf.doctype.huf_data_table.api.get_table_schema', {
			name,
		});
		return result.message as DataTableSchema;
	} catch (error) {
		handleFrappeError(error, 'Error fetching table schema');
	}
}

/**
 * Create a new data table
 */
export async function createDataTable(data: {
	table_name: string;
	fields: DataTableFieldDef[];
	description?: string;
	icon?: string;
	autoname_method?: string;
	title_field?: string;
}): Promise<{ name: string; table_name: string; doctype_name: string }> {
	try {
		const result = await call.post('huf.huf.doctype.huf_data_table.api.create_data_table', data);
		return result.message.data;
	} catch (error) {
		handleFrappeError(error, 'Error creating data table');
	}
}

/**
 * Update a data table structure
 */
export async function updateDataTable(
	name: string,
	data: {
		fields?: DataTableFieldDef[];
		description?: string;
		icon?: string;
	}
): Promise<void> {
	try {
		await call.post('huf.huf.doctype.huf_data_table.api.update_data_table', { name, ...data });
	} catch (error) {
		handleFrappeError(error, 'Error updating data table');
	}
}

/**
 * Delete a data table
 */
export async function deleteDataTable(name: string): Promise<{ deleted_records: number }> {
	try {
		const result = await call.post('huf.huf.doctype.huf_data_table.api.delete_data_table', {
			name,
		});
		return result.message.data;
	} catch (error) {
		handleFrappeError(error, 'Error deleting data table');
	}
}

/**
 * Get list of Huf table names (for Link field target selection)
 */
export async function getHufTableNames(): Promise<
	Array<{ table_name: string; doctype_name: string }>
> {
	try {
		const result = await call.get('huf.huf.doctype.huf_data_table.api.get_huf_table_names');
		return result.message;
	} catch (error) {
		handleFrappeError(error, 'Error fetching table names');
	}
}

// ─── Record CRUD (uses standard Frappe SDK directly) ───

/**
 * Get records from a data table
 */
export async function getTableRecords(
	doctypeName: string,
	params?: {
		fields?: string[];
		filters?: Array<[string, string, unknown]>;
		limit?: number;
		start?: number;
		orderBy?: { field: string; order: 'asc' | 'desc' };
	}
): Promise<{ items: Record<string, unknown>[]; hasMore: boolean }> {
	try {
		const limit = params?.limit || 20;
		const records = await db.getDocList(doctypeName, {
			fields: params?.fields || ['*'],
			filters: params?.filters as any,
			limit: limit + 1,
			...(params?.start && { limit_start: params.start }),
			orderBy: params?.orderBy || { field: 'modified', order: 'desc' },
		});

		const hasMore = records.length > limit;
		const items = hasMore ? records.slice(0, limit) : records;

		return { items: items as Record<string, unknown>[], hasMore };
	} catch (error) {
		handleFrappeError(error, 'Error fetching records');
	}
}

/**
 * Get a single record
 */
export async function getTableRecord(
	doctypeName: string,
	recordName: string
): Promise<Record<string, unknown>> {
	try {
		return (await db.getDoc(doctypeName, recordName)) as Record<string, unknown>;
	} catch (error) {
		handleFrappeError(error, 'Error fetching record');
	}
}

/**
 * Create a record in a data table
 */
export async function createTableRecord(
	doctypeName: string,
	data: Record<string, unknown>
): Promise<Record<string, unknown>> {
	try {
		return (await db.createDoc(doctypeName, data)) as Record<string, unknown>;
	} catch (error) {
		handleFrappeError(error, 'Error creating record');
	}
}

/**
 * Update a record
 */
export async function updateTableRecord(
	doctypeName: string,
	recordName: string,
	data: Record<string, unknown>
): Promise<void> {
	try {
		await db.updateDoc(doctypeName, recordName, data);
	} catch (error) {
		handleFrappeError(error, 'Error updating record');
	}
}

/**
 * Delete a record
 */
export async function deleteTableRecord(doctypeName: string, recordName: string): Promise<void> {
	try {
		await db.deleteDoc(doctypeName, recordName);
	} catch (error) {
		handleFrappeError(error, 'Error deleting record');
	}
}
