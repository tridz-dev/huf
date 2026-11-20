import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { isNumeric, type GridColumn } from '@/components/grid';
import type { Row } from './model';

export interface ValueInputProps {
	col: GridColumn<Row>;
	/** Text form of the value ("Yes"/"No" for checkbox). */
	value: string;
	onChange: (value: string) => void;
	onBlur?: () => void;
	id?: string;
	invalid?: boolean;
	describedBy?: string;
}

/** One input per column type, shared by the filter editor, set-value and record drawer. */
export function ValueInput({ col, value, onChange, onBlur, id, invalid, describedBy }: ValueInputProps) {
	const aria = { 'aria-invalid': invalid || undefined, 'aria-describedby': describedBy };
	if (col.type === 'checkbox') {
		return (
			<Checkbox
				id={id}
				checked={value === 'Yes'}
				onCheckedChange={(v) => {
					onChange(v === true ? 'Yes' : 'No');
				}}
				onBlur={onBlur}
				{...aria}
			/>
		);
	}
	if (col.type === 'select') {
		return (
			<Select
				value={value || undefined}
				onValueChange={(v) => {
					onChange(v);
					onBlur?.();
				}}
			>
				<SelectTrigger id={id} {...aria}>
					<SelectValue placeholder="Choose…" />
				</SelectTrigger>
				<SelectContent>
					{(col.options ?? []).map((o) => (
						<SelectItem key={o.value} value={o.value}>
							{o.label ?? o.value}
						</SelectItem>
					))}
				</SelectContent>
			</Select>
		);
	}
	if (col.type === 'longtext') {
		return <Textarea id={id} value={value} onChange={(e) => onChange(e.target.value)} onBlur={onBlur} {...aria} />;
	}
	return (
		<Input
			id={id}
			type={col.type === 'date' ? 'date' : 'text'}
			inputMode={isNumeric(col.type) ? 'decimal' : undefined}
			value={value}
			onChange={(e) => onChange(e.target.value)}
			onBlur={onBlur}
			{...aria}
		/>
	);
}
