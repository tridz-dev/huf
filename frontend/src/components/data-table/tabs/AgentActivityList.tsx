import { useEffect, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { ResourceList, ResourceRow } from '@/components/patterns';
import { getTableAgentActivity } from '@/services/dataTableApi';
import type { TableAgentActivityItem } from '@/types/dataTable.types';

const isBlocked = (s: string) => /block|denied|fail|error/i.test(s);

export function AgentActivityList({ tableId }: { tableId: string }) {
	const [items, setItems] = useState<TableAgentActivityItem[] | null>(null);

	useEffect(() => {
		let live = true;
		getTableAgentActivity(tableId, 10).then(
			(r) => live && setItems(r),
			() => live && setItems([]),
		);
		return () => {
			live = false;
		};
	}, [tableId]);

	if (items === null) return <p className="text-ui-text text-steel">Loading recent calls</p>;
	if (items.length === 0) return <p className="text-ui-text text-steel">No agent has used this table yet.</p>;
	return (
		<ResourceList label="Recent agent calls" columns={['Call', 'Agent', 'Result', 'When']}>
			{items.map((i, n) => (
				<ResourceRow
					key={`${i.timestamp}-${n}`}
					title={i.tool}
					origin={i.agent}
					status={
						<Badge variant={isBlocked(i.status) ? 'pill-danger' : 'pill-success'}>
							{isBlocked(i.status) ? 'Blocked' : 'Allowed'}
						</Badge>
					}
					time={i.timestamp}
				/>
			))}
		</ResourceList>
	);
}
