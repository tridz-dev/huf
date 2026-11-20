import { useEffect, useState } from 'react';
import { Field } from '@/components/ui/field';
import { RecordDrawer, formatCell, parseCell, type CellValue, type GridColumn } from '@/components/grid';
import type { Row } from './model';
import { ValueInput } from './ValueInput';

export interface RecordPanelProps {
	row: Row | null;
	columns: GridColumn<Row>[];
	position?: { index: number; total: number };
	onClose: () => void;
	onPrev?: () => void;
	onNext?: () => void;
	/** Persist one field; resolve a message to reject it. */
	onChange: (rowId: string, key: string, value: CellValue) => Promise<string | null | void> | string | null | void;
}

const toText = (col: GridColumn<Row>, v: CellValue): string =>
	col.type === 'checkbox' ? (v ? 'Yes' : 'No') : col.type === 'date' || col.type === 'select' ? (v == null ? '' : String(v)) : formatCell({ type: 'text' }, v);

/** One record in the right sheet; each field saves when you leave it. */
export function RecordPanel({ row, columns, position, onClose, onPrev, onNext, onChange }: RecordPanelProps) {
	const [draft, setDraft] = useState<Record<string, string>>({});
	const [errors, setErrors] = useState<Record<string, string>>({});
	const rowName = row?.name;

	useEffect(() => {
		if (!row) return;
		setDraft(Object.fromEntries(columns.map((c) => [c.key, toText(c, row[c.key])])));
		setErrors({});
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [rowName]);

	if (!row) return null;
	const titleCol = columns.find((c) => c.tag === 'title') ?? columns[0];

	const save = async (col: GridColumn<Row>) => {
		const text = draft[col.key] ?? '';
		if (text === toText(col, row[col.key])) return;
		let value: CellValue;
		if (col.type === 'checkbox') value = text === 'Yes';
		else {
			const parsed = parseCell(col.type, text);
			if ('error' in parsed) return setErrors((e) => ({ ...e, [col.key]: parsed.error }));
			value = parsed.value;
		}
		const msg = await onChange(row.name, col.key, value);
		setErrors((e) => {
			const next = { ...e };
			if (typeof msg === 'string') next[col.key] = msg;
			else delete next[col.key];
			return next;
		});
	};

	return (
		<RecordDrawer
			open
			onOpenChange={(o) => !o && onClose()}
			title={String(row[titleCol?.key ?? ''] || row.name)}
			subtitle={row.name}
			position={position}
			onPrev={onPrev}
			onNext={onNext}
		>
			{columns.map((c) => (
				<Field key={c.key} label={c.label} required={c.required} error={errors[c.key]}>
					{(p) => (
						<ValueInput
							col={c}
							id={p.id}
							value={draft[c.key] ?? ''}
							invalid={!!errors[c.key]}
							describedBy={p['aria-describedby']}
							onChange={(v) => setDraft((d) => ({ ...d, [c.key]: v }))}
							onBlur={() => void save(c)}
						/>
					)}
				</Field>
			))}
		</RecordDrawer>
	);
}
