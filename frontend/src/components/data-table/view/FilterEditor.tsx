import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { GridColumn } from '@/components/grid';
import { needsValue, opsFor, type FilterCond, type FilterOp, type Row } from './model';
import { ValueInput } from './ValueInput';

export interface FilterEditorProps {
	columns: GridColumn<Row>[];
	initial?: FilterCond;
	submitLabel?: string;
	onSubmit: (cond: FilterCond) => void;
}

/** Edits one condition: field, operator in plain words, value. */
export function FilterEditor({ columns, initial, submitLabel = 'Apply', onSubmit }: FilterEditorProps) {
	const [field, setField] = useState(initial?.field ?? columns[0]?.key ?? '');
	const [op, setOp] = useState<FilterOp>(initial?.op ?? 'is');
	const [value, setValue] = useState(initial?.value ?? '');
	const col = columns.find((c) => c.key === field) ?? columns[0];
	if (!col) return null;
	const ops = opsFor(col.type);
	const effectiveOp = ops.includes(op) ? op : ops[0];
	const ready = !needsValue(effectiveOp) || value.trim() !== '' || col.type === 'checkbox';

	const pickField = (key: string) => {
		setField(key);
		setValue('');
		const next = columns.find((c) => c.key === key);
		if (next && !opsFor(next.type).includes(op)) setOp(opsFor(next.type)[0]);
	};

	return (
		<form
			className="space-y-3"
			onSubmit={(e) => {
				e.preventDefault();
				if (ready) onSubmit({ field: col.key, op: effectiveOp, value: col.type === 'checkbox' && !value ? 'No' : value });
			}}
		>
			<Field label="Field">
				<Select value={col.key} onValueChange={pickField}>
					<SelectTrigger>
						<SelectValue />
					</SelectTrigger>
					<SelectContent>
						{columns.map((c) => (
							<SelectItem key={c.key} value={c.key}>
								{c.label}
							</SelectItem>
						))}
					</SelectContent>
				</Select>
			</Field>
			<Field label="Condition">
				<Select value={effectiveOp} onValueChange={(v) => setOp(v as FilterOp)}>
					<SelectTrigger>
						<SelectValue />
					</SelectTrigger>
					<SelectContent>
						{ops.map((o) => (
							<SelectItem key={o} value={o}>
								{o}
							</SelectItem>
						))}
					</SelectContent>
				</Select>
			</Field>
			{needsValue(effectiveOp) && (
				<Field label="Value">
					{(p) => <ValueInput col={col} value={value} onChange={setValue} id={p.id} />}
				</Field>
			)}
			<Button type="submit" size="sm" disabled={!ready}>
				{submitLabel}
			</Button>
		</form>
	);
}
