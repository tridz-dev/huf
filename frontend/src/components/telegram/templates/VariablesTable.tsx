import { Input } from '@/components/ui/input';
import type { TemplateVariable } from '@/services/telegramTemplatesApi';

export interface VariablesTableProps {
	rows: TemplateVariable[];
	onChange: (rows: TemplateVariable[]) => void;
	error?: string;
}

/** One row per {{variable}} found in the text. Names come from the text; only defaults and examples are edited. */
export function VariablesTable({ rows, onChange, error }: VariablesTableProps) {
	if (!rows.length) {
		return <p className="text-sm text-steel">No variables yet. Type {'{{name}}'} in the message to add one.</p>;
	}
	const set = (i: number, patch: Partial<TemplateVariable>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
	return (
		<div className="space-y-2">
			<div className="hidden grid-cols-[1fr_1fr_1fr] gap-2 text-xs font-medium text-steel sm:grid">
				<span>Variable</span><span>Default (used when empty)</span><span>Example (preview only)</span>
			</div>
			{rows.map((r, i) => (
				<div key={r.variable} className="grid gap-2 sm:grid-cols-[1fr_1fr_1fr]">
					<code className="self-center truncate font-mono text-sm text-ink">{`{{${r.variable}}}`}</code>
					<Input aria-label={`Default for ${r.variable}`} placeholder="Default" value={r.default_value} onChange={(e) => set(i, { default_value: e.target.value })} />
					<Input aria-label={`Example for ${r.variable}`} placeholder="Example" value={r.example} onChange={(e) => set(i, { example: e.target.value })} />
				</div>
			))}
			{error && <p role="alert" className="text-xs text-danger">{error}</p>}
		</div>
	);
}
