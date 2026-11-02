import { useMemo } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
	BUTTON_KINDS, MAX_PER_ROW, MAX_ROWS, buttonsToJson, parseButtons, validateButtons,
	type ButtonKind, type ButtonsModel, type EditorButton,
} from './previewModel';

const KIND_LABEL: Record<ButtonKind, string> = {
	callback: 'Reply (button id)', url: 'Open link', web_app: 'Open mini app', switch_inline: 'Inline query',
	copy_text: 'Copy text', login_url: 'Log in via link',
};
const VALUE_PLACEHOLDER: Record<ButtonKind, string> = {
	callback: 'approve:42', url: 'https://example.com', web_app: 'https://app.example.com', switch_inline: 'search term',
	copy_text: 'Text to copy', login_url: 'https://example.com/login',
};

export interface ButtonsEditorProps {
	/** The telegram-buttons JSON (empty string = no buttons). */
	value: string;
	onChange: (json: string) => void;
	error?: string;
}

export function ButtonsEditor({ value, onChange, error }: ButtonsEditorProps) {
	const model = useMemo(() => parseButtons(value), [value]);
	if (!model) {
		return (
			<div className="space-y-2 text-sm">
				<p className="text-steel">These buttons use a layout this editor cannot show. You can clear them and start again.</p>
				<Button type="button" variant="outline" size="sm" onClick={() => onChange('')}>Clear buttons</Button>
			</div>
		);
	}
	const emit = (m: ButtonsModel) => onChange(buttonsToJson({ ...m, rows: m.rows.filter((r) => r.length) }));
	// Rows with no buttons are kept out of the JSON, so edit against a model that always has a trailing slot.
	const setButton = (ri: number, bi: number, patch: Partial<EditorButton>) =>
		emit({ ...model, rows: model.rows.map((r, i) => (i === ri ? r.map((b, j) => (j === bi ? { ...b, ...patch } : b)) : r)) });
	const removeButton = (ri: number, bi: number) =>
		emit({ ...model, rows: model.rows.map((r, i) => (i === ri ? r.filter((_, j) => j !== bi) : r)) });
	const addToRow = (ri: number) =>
		emit({ ...model, rows: model.rows.map((r, i) => (i === ri ? [...r, { text: '', kind: 'callback' as const, value: '' }] : r)) });
	const addRow = () => emit({ ...model, rows: [...model.rows, [{ text: '', kind: 'callback', value: '' }]] });
	const problems = validateButtons(model);

	return (
		<div className="space-y-3">
			{model.rows.map((row, ri) => (
				<div key={ri} className="space-y-2 rounded-md border border-line p-2" aria-label={`Button row ${ri + 1}`}>
					{row.map((b, bi) => (
						<div key={bi} className="grid gap-2 sm:grid-cols-[1fr_9rem_1.4fr_auto]">
							<Input aria-label={`Row ${ri + 1} button ${bi + 1} label`} placeholder="Label" value={b.text} maxLength={64} onChange={(e) => setButton(ri, bi, { text: e.target.value })} />
							<Select value={b.kind} onValueChange={(k) => setButton(ri, bi, { kind: k as ButtonKind })}>
								<SelectTrigger aria-label={`Row ${ri + 1} button ${bi + 1} type`}><SelectValue /></SelectTrigger>
								<SelectContent>
									{BUTTON_KINDS.map((k) => <SelectItem key={k} value={k}>{KIND_LABEL[k]}</SelectItem>)}
								</SelectContent>
							</Select>
							<Input aria-label={`Row ${ri + 1} button ${bi + 1} value`} placeholder={VALUE_PLACEHOLDER[b.kind]} value={b.value} onChange={(e) => setButton(ri, bi, { value: e.target.value })} />
							<Button type="button" variant="ghost" size="icon" aria-label={`Remove row ${ri + 1} button ${bi + 1}`} onClick={() => removeButton(ri, bi)}>
								<Trash2 className="h-4 w-4" />
							</Button>
						</div>
					))}
					<Button type="button" variant="ghost" size="sm" disabled={row.length >= MAX_PER_ROW} onClick={() => addToRow(ri)}>
						<Plus className="mr-1 h-3.5 w-3.5" />Add beside
					</Button>
				</div>
			))}
			<Button type="button" variant="outline" size="sm" disabled={model.rows.length >= MAX_ROWS} onClick={addRow}>
				<Plus className="mr-1 h-3.5 w-3.5" />Add button row
			</Button>
			{model.rows.length > 0 && (
				<div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
					<label className="flex items-center gap-2"><Switch checked={model.once} onCheckedChange={(once) => emit({ ...model, once })} />Remove buttons after the first press</label>
					<label className="flex items-center gap-2"><Switch checked={model.edit} onCheckedChange={(edit) => emit({ ...model, edit })} />Edit the message when answering a press</label>
				</div>
			)}
			{[...problems, ...(error ? [error] : [])].map((p) => <p key={p} role="alert" className="text-xs text-danger">{p}</p>)}
		</div>
	);
}
