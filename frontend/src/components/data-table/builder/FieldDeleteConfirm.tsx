import { ConfirmDestructive, type Dependent } from '@/components/grid';

interface FieldDeleteConfirmProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	fieldLabel: string;
	/** Rows in the table, when known. There is no per-column value count endpoint yet. */
	recordCount?: number;
	dependents: Dependent[];
	onConfirm: () => void;
}

/** Confirm removing a column that already exists (and so holds data). */
export function FieldDeleteConfirm({ open, onOpenChange, fieldLabel, recordCount, dependents, onConfirm }: FieldDeleteConfirmProps) {
	const name = fieldLabel || 'this field';
	const consequence =
		recordCount != null
			? `Removes the "${name}" column and its values from ${recordCount.toLocaleString()} ${recordCount === 1 ? 'row' : 'rows'}.`
			: `Removes the "${name}" column and its data.`;
	return (
		<ConfirmDestructive
			open={open}
			onOpenChange={onOpenChange}
			title={`Delete field "${name}"?`}
			consequence={consequence}
			recovery="This happens when you save changes, and the values can't be restored."
			dependents={dependents}
			actionLabel="Delete field"
			onConfirm={onConfirm}
		/>
	);
}
