import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { ResourceList, ResourceRow } from '@/components/patterns';
import { getTableAgentActivity } from '@/services/dataTableApi';
import type { TableAgentActivityItem } from '@/types/dataTable.types';

const statusTone = (s: string): 'pill-success' | 'pill-danger' | 'pill-neutral' =>
	/success|ok|done|completed/i.test(s) ? 'pill-success' : /fail|error|block|denied/i.test(s) ? 'pill-danger' : 'pill-neutral';

/** Recent agent calls on this table. Empty and failure are quiet, never an error screen. */
export function ActivityTab({ tableId }: { tableId: string }) {
	const [items, setItems] = useState<TableAgentActivityItem[] | null>(null);

	useEffect(() => {
		let live = true;
		getTableAgentActivity(tableId)
			.then((r) => live && setItems(r))
			.catch(() => live && setItems([]));
		return () => {
			live = false;
		};
	}, [tableId]);

	if (items === null) return <p className="py-6 text-ui-text text-steel">Loading activity…</p>;
	if (items.length === 0) {
		return <p className="py-6 text-ui-text text-steel">No agent has used this table yet. Calls from agents show up here.</p>;
	}
	return (
		<ResourceList label="Recent agent calls" columns={['Agent', 'Tool', 'Status', 'When']}>
			{items.map((it, i) => (
				<ResourceRow
					key={`${it.agent}-${it.timestamp}-${i}`}
					title={it.agent}
					origin={it.tool}
					status={<Badge variant={statusTone(it.status)}>{it.status}</Badge>}
					time={it.timestamp}
				/>
			))}
		</ResourceList>
	);
}
