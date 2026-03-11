import { useEffect, useState, ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { DataTableViewPage } from './DataTableViewPage';
import { getTableSchema } from '../services/dataTableApi';

export function DataTableViewWrapper() {
	const { tableId } = useParams<{ tableId: string }>();
	const [tableName, setTableName] = useState<string>('Table');
	const [headerActions, setHeaderActions] = useState<ReactNode>(null);

	useEffect(() => {
		if (tableId) {
			getTableSchema(tableId)
				.then((schema) => {
					setTableName(schema.table_name);
				})
				.catch(() => {
					setTableName('Table');
				});
		}
	}, [tableId]);

	const breadcrumbs = [
		{ label: 'Data', href: '/data' },
		{ label: tableName },
	];

	return (
		<UnifiedLayout breadcrumbs={breadcrumbs} headerActions={headerActions}>
			<DataTableViewPage onHeaderActionsChange={setHeaderActions} />
		</UnifiedLayout>
	);
}
