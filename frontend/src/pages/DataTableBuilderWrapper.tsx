import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { DataTableBuilderPage } from './DataTableBuilderPage';
import { getTableSchema } from '../services/dataTableApi';

export function DataTableBuilderWrapper() {
	const { tableId } = useParams<{ tableId: string }>();
	const isEdit = !!tableId && tableId !== 'new';
	const [tableName, setTableName] = useState<string>(isEdit ? 'Edit table' : 'New table');

	useEffect(() => {
		if (isEdit) {
			getTableSchema(tableId)
				.then((schema) => {
					setTableName(schema.table_name);
				})
				.catch(() => {
					setTableName('Edit Table');
				});
		}
	}, [tableId, isEdit]);

	const breadcrumbs = isEdit
		? [
				{ label: 'Data', href: '/data' },
				{ label: tableName, href: `/data/${tableId}` },
				{ label: 'Edit' },
			]
		: [{ label: 'Data', href: '/data' }, { label: 'New table' }];

	return (
		<UnifiedLayout breadcrumbs={breadcrumbs}>
			<DataTableBuilderPage />
		</UnifiedLayout>
	);
}
