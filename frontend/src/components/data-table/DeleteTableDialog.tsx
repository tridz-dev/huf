import { useEffect, useState } from 'react';
import { ConfirmDestructive, type Dependent } from '@/components/grid';
import { getTableDependencies } from '@/services/dataTableApi';

interface DeleteTableDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	tableName: string;
	recordCount: number;
	onConfirm: () => void;
	loading?: boolean;
	/** Registry id for the dependency lookup; defaults to tableName. */
	tableId?: string;
}

export function DeleteTableDialog({
	open,
	onOpenChange,
	tableName,
	recordCount,
	onConfirm,
	tableId,
}: DeleteTableDialogProps) {
	const [dependents, setDependents] = useState<Dependent[]>([]);
	const [liveCount, setLiveCount] = useState<number | null>(null);

	useEffect(() => {
		if (!open || !tableName) return;
		let live = true;
		getTableDependencies(tableId || tableName)
			.then((d) => {
				if (!live) return;
				setLiveCount(d.record_count);
				setDependents([
					...d.agents.map((a) => ({ kind: 'Agent', label: a.agent_name || a.agent })),
					...d.flows.map((f) => ({ kind: 'Flow', label: f.title || f.name })),
				]);
			})
			.catch(() => {
				// Endpoint missing or failed: fall back to the count the caller gave us.
				if (live) { setLiveCount(null); setDependents([]); }
			});
		return () => { live = false; };
	}, [open, tableName, tableId]);

	const rows = liveCount ?? recordCount;
	const consequence =
		rows > 0
			? `Removes the table and all ${rows.toLocaleString()} ${rows === 1 ? 'row' : 'rows'} in it.`
			: 'Removes the table and its fields.';
	return (
		<ConfirmDestructive
			open={open}
			onOpenChange={onOpenChange}
			title={`Delete "${tableName}"?`}
			consequence={consequence}
			// Hard delete today: do not promise a restore window.
			recovery="This can't be undone."
			dependents={dependents}
			confirmText={tableName}
			actionLabel="Delete table"
			onConfirm={onConfirm}
		/>
	);
}
