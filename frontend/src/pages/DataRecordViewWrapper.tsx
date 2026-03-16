import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';
import { DataRecordViewPage } from '@/pages/DataRecordViewPage';
import { getTableSchema } from '@/services/dataTableApi';
import type { DataTableSchema } from '../types/dataTable.types';

export default function DataRecordViewWrapper() {
	const { tableId, recordName } = useParams<{ tableId: string; recordName: string }>();
	const navigate = useNavigate();
	const [schema, setSchema] = useState<DataTableSchema | null>(null);
	const [headerActions, setHeaderActions] = useState<ReactNode>(null);

	useEffect(() => {
		if (!tableId) return;
		getTableSchema(tableId)
			.then((result) => {
				setSchema(result);
			})
			.catch(() => {
				navigate('/data');
			});
	}, [tableId, navigate]);

	const tableLabel = schema?.table_name ?? 'Table';
	const recordLabel = recordName === 'new' ? 'New Record' : recordName ?? 'Record';

	const breadcrumbs = [
		{ label: 'Data', href: '/data' },
		{ label: tableLabel, href: tableId ? `/data/${tableId}` : undefined },
		{ label: recordLabel },
	];

	return (
		<UnifiedLayout breadcrumbs={breadcrumbs} headerActions={headerActions}>
			<DataRecordViewPage
				schema={schema}
				onHeaderActionsChange={setHeaderActions}
			/>
		</UnifiedLayout>
	);
}

