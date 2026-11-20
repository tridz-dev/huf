import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Field } from '@/components/ui/field';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { parseCell, type CellValue, type GridColumn } from '@/components/grid';
import type { Row } from './model';
import { ValueInput } from './ValueInput';

export interface SetValueDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	columns: GridColumn<Row>[];
	count: number;
	onApply: (key: string, value: CellValue) => Promise<void> | void;
}

export function SetValueDialog({ open, onOpenChange, columns, count, onApply }: SetValueDialogProps) {
	const editable = columns.filter((c) => !c.readOnly);
	const [key, setKey] = useState('');
	const [text, setText] = useState('');
	const [error, setError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);
	const col = editable.find((c) => c.key === key) ?? editable[0];
	if (!col) return null;

	const submit = async () => {
		let value: CellValue;
		if (col.type === 'checkbox') value = text === 'Yes';
		else {
			const parsed = parseCell(col.type, text);
			if ('error' in parsed) return setError(parsed.error);
			value = parsed.value;
		}
		setBusy(true);
		try {
			await onApply(col.key, value);
			onOpenChange(false);
			setText('');
			setError(null);
		} finally {
			setBusy(false);
		}
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent>
				<DialogHeader>
					<DialogTitle>Set a value</DialogTitle>
					<DialogDescription>Sets one field on {count.toLocaleString()} selected {count === 1 ? 'row' : 'rows'}.</DialogDescription>
				</DialogHeader>
				<Field label="Field">
					<Select
						value={col.key}
						onValueChange={(v) => {
							setKey(v);
							setText('');
							setError(null);
						}}
					>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							{editable.map((c) => (
								<SelectItem key={c.key} value={c.key}>
									{c.label}
								</SelectItem>
							))}
						</SelectContent>
					</Select>
				</Field>
				<Field label="New value" error={error ?? undefined}>
					{(p) => <ValueInput col={col} value={text} onChange={setText} id={p.id} invalid={!!error} describedBy={p['aria-describedby']} />}
				</Field>
				<DialogFooter>
					<Button variant="outline" onClick={() => onOpenChange(false)}>
						Cancel
					</Button>
					<Button onClick={submit} disabled={busy}>
						Set value
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	);
}
