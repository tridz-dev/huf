/**
 * Renders a frappe-form artifact payload (see
 * huf/ai/tools/frappe_generic.py::handle_render_frappe_view, mode="form") as
 * a read/edit-view form driven by `meta.fields`.
 *
 * This is a draft-review UI only, matching the backend's draft-only write
 * contract (handle_create_record/handle_update_record never write to the
 * database - they hand back a `{"draft": true, ...}` payload for the human
 * to actually submit through the normal Frappe REST path). There is
 * therefore no submit-to-backend wiring here yet.
 */

import { useMemo, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Button } from '@/components/ui/button';
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from '@/components/ui/select';
import { CopyIcon, CheckIcon, ExternalLink } from 'lucide-react';
import type { FrappeFieldMeta, FrappeViewPayload } from '@/types/artifact.types';
import { isDisplayField } from './frappeFieldFormat';
import { deskFormUrl } from './frappeDeskUrl';

export interface FrappeFormViewProps {
	payload: FrappeViewPayload;
}

/** Fieldtypes rendered as a plain (possibly disabled) text input. */
const TEXT_LIKE_FIELDTYPES = new Set([
	'Data',
	'Text',
	'Small Text',
	'Long Text',
	'Text Editor',
	'Code',
	'Link',
	'Dynamic Link',
	'Int',
	'Float',
	'Currency',
	'Percent',
	'Date',
	'Datetime',
	'Time',
	'Password',
]);

export function FrappeFormView({ payload }: FrappeFormViewProps) {
	const record = useMemo(
		() => (Array.isArray(payload.data) ? payload.data[0] ?? {} : payload.data ?? {}),
		[payload.data]
	);

	const fields = useMemo<FrappeFieldMeta[]>(
		() => (payload.meta?.fields ?? []).filter(isDisplayField),
		[payload.meta]
	);

	const [values, setValues] = useState<Record<string, unknown>>(record);
	const [copied, setCopied] = useState(false);

	const setValue = (fieldname: string, value: unknown) => {
		setValues((prev) => ({ ...prev, [fieldname]: value }));
	};

	// TODO: no submit-to-backend wiring yet - this is a draft-review UI per
	// the backend's draft-only contract (handle_create_record /
	// handle_update_record only ever return a draft payload; the actual
	// write happens client-side via the normal Frappe REST API as the
	// logged-in user). For now, "submit" just copies the edited values as
	// JSON so a human can inspect/paste them elsewhere.
	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();
		console.log('[FrappeFormView] draft submit (TODO: wire to backend)', {
			doctype: payload.doctype,
			values,
		});
		try {
			await navigator.clipboard.writeText(JSON.stringify(values, null, 2));
			setCopied(true);
			setTimeout(() => setCopied(false), 2000);
		} catch (err) {
			console.error('Failed to copy draft values:', err);
		}
	};

	const recordName = typeof record.name === 'string' ? record.name : undefined;

	return (
		<form onSubmit={handleSubmit} className="space-y-3 rounded-sm border border-line bg-panel p-3.5">
			{recordName && (
				<div className="flex items-center justify-between border-b border-line pb-2">
					<span className="font-mono text-[11px] uppercase tracking-wide text-steel-soft">
						{recordName}
					</span>
					<a
						href={deskFormUrl(payload.doctype, recordName)}
						target="_blank"
						rel="noopener noreferrer"
						className="inline-flex items-center gap-1 text-xs text-steel hover:text-ink"
					>
						Open in Desk
						<ExternalLink className="h-3 w-3" />
					</a>
				</div>
			)}
			<div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-3">
				{fields.map((field) => (
					<div key={field.fieldname} className="space-y-1">
						<Label
							htmlFor={field.fieldname}
							className="font-mono text-[10px] uppercase tracking-wide text-steel-soft"
						>
							{field.label || field.fieldname}
							{field.reqd && <span className="text-destructive ml-0.5">*</span>}
						</Label>
						{renderFieldControl(field, values[field.fieldname], (v) => setValue(field.fieldname, v))}
					</div>
				))}
			</div>
			<div className="flex justify-end pt-1">
				<Button type="submit" size="sm" variant="outline" className="h-7 px-2 text-xs">
					{copied ? <CheckIcon className="h-3.5 w-3.5 mr-1" /> : <CopyIcon className="h-3.5 w-3.5 mr-1" />}
					{copied ? 'Copied as JSON' : 'Copy as JSON'}
				</Button>
			</div>
		</form>
	);
}

function renderFieldControl(
	field: FrappeFieldMeta,
	value: unknown,
	onChange: (value: unknown) => void
) {
	if (field.fieldtype === 'Check') {
		return (
			<Checkbox
				id={field.fieldname}
				className="rounded-sm"
				checked={Boolean(value)}
				disabled={field.read_only}
				onCheckedChange={(checked) => onChange(Boolean(checked))}
			/>
		);
	}

	if (field.fieldtype === 'Select') {
		const options = field.select_options ?? [];
		return (
			<Select
				value={value != null ? String(value) : undefined}
				disabled={field.read_only}
				onValueChange={(v) => onChange(v)}
			>
				<SelectTrigger id={field.fieldname} size="sm" className="rounded-sm">
					<SelectValue placeholder="Select..." />
				</SelectTrigger>
				<SelectContent>
					{options.map((opt) => (
						<SelectItem key={opt} value={opt}>
							{opt}
						</SelectItem>
					))}
				</SelectContent>
			</Select>
		);
	}

	// Everything else (Data/Text/Link/Int/Currency/Date/... and any fieldtype
	// this view doesn't special-case) falls back to a plain text input -
	// including Table, which shows the raw child-row count rather than an
	// editable grid (out of scope here).
	const isKnownTextLike = TEXT_LIKE_FIELDTYPES.has(field.fieldtype);
	const displayValue =
		field.fieldtype === 'Table' && Array.isArray(value)
			? `${value.length} row(s)`
			: value != null
				? String(value)
				: '';

	return (
		<Input
			id={field.fieldname}
			size="sm"
			className="rounded-sm"
			value={displayValue}
			disabled={field.read_only || field.fieldtype === 'Table'}
			onChange={(e) => onChange(e.target.value)}
			placeholder={!isKnownTextLike ? field.fieldtype : undefined}
		/>
	);
}

export default FrappeFormView;
