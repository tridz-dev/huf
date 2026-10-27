import { useMemo, useRef, useState } from 'react';
import { Loader2, Paperclip, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
	MEDIA_TYPES, PARSE_MODES, TEXT_LIMIT, mediaTypeLabel, problemsByField, syncVariables, uploadTemplateMedia,
	validateDraft, type MediaType, type ParseMode, type TemplateDraft,
} from '@/services/telegramTemplatesApi';
import { ButtonsEditor } from './ButtonsEditor';
import { TemplatePreview } from './TemplatePreview';
import { VariablesTable } from './VariablesTable';

const MODE_HELP: Record<ParseMode, string> = {
	HTML: 'Use <b>bold</b>, <i>italic</i>, <a href="...">links</a>, <code>code</code>.',
	MarkdownV2: 'Use *bold*, _italic_, [links](https://...). Escape . ! - ( ) with a backslash.',
	Plain: 'Sent exactly as typed, with no formatting.',
};
const ACCEPT: Partial<Record<MediaType, string>> = {
	photo: 'image/*', video: 'video/*', animation: 'image/gif,video/mp4', audio: 'audio/*', voice: 'audio/ogg,audio/*', sticker: 'image/webp,.tgs',
};

export interface TemplateEditorProps {
	draft: TemplateDraft;
	onChange: (draft: TemplateDraft) => void;
	onSave: () => void;
	onCancel: () => void;
	saving?: boolean;
	/** Field errors returned by the server on the last save. */
	serverErrors?: Record<string, string>;
	/** Gateways the template can be limited to. */
	gateways?: string[];
}

function Field({ id, label, error, hint, children }: { id: string; label: string; error?: string; hint?: string; children: React.ReactNode }) {
	return (
		<div className="space-y-1">
			<Label htmlFor={id}>{label}</Label>
			{children}
			{hint && !error && <p className="text-xs text-steel">{hint}</p>}
			{error && <p role="alert" className="text-xs text-danger">{error}</p>}
		</div>
	);
}

export function TemplateEditor({ draft, onChange, onSave, onCancel, saving, serverErrors, gateways = [] }: TemplateEditorProps) {
	const [touched, setTouched] = useState(false);
	const [uploading, setUploading] = useState(false);
	const [uploadError, setUploadError] = useState('');
	const bodyRef = useRef<HTMLTextAreaElement>(null);
	const fileRef = useRef<HTMLInputElement>(null);
	const [newVar, setNewVar] = useState('');
	const [typed, setTyped] = useState<Record<string, string>>({});

	const clientErrors = useMemo(() => problemsByField(validateDraft(draft)), [draft]);
	const errors = { ...serverErrors, ...(touched ? clientErrors : {}) };
	const hasMedia = draft.media_type !== 'none';
	const limit = TEXT_LIMIT;

	const patch = (p: Partial<TemplateDraft>) => {
		const next = { ...draft, ...p };
		onChange({ ...next, variables: syncVariables(next.variables, next.body, next.buttons_json) });
	};

	const insertVariable = () => {
		const name = newVar.trim();
		if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) return;
		setNewVar('');
		const el = bodyRef.current;
		const at = el?.selectionStart ?? draft.body.length;
		const end = el?.selectionEnd ?? at;
		patch({ body: `${draft.body.slice(0, at)}{{${name}}}${draft.body.slice(end)}` });
		el?.focus();
	};

	const upload = async (f: File | undefined) => {
		if (!f) return;
		setUploading(true);
		setUploadError('');
		const res = await uploadTemplateMedia(f);
		setUploading(false);
		if (res.ok) patch({ media: res.data.fileUrl });
		else setUploadError(res.error);
	};

	const save = () => {
		setTouched(true);
		if (Object.keys(problemsByField(validateDraft(draft))).length === 0) onSave();
	};

	return (
		<div className="grid gap-6 lg:grid-cols-[1fr_340px]">
			<form className="space-y-5" onSubmit={(e) => { e.preventDefault(); save(); }} noValidate>
				<div className="grid gap-3 sm:grid-cols-2">
					<Field id="tg-tpl-name" label="Name" error={errors.template_name} hint="Shown in lists and when the agent picks a template.">
						<Input id="tg-tpl-name" value={draft.template_name} onChange={(e) => patch({ template_name: e.target.value })} />
					</Field>
					<Field id="tg-tpl-lang" label="Language" error={errors.language}>
						<Input id="tg-tpl-lang" value={draft.language} placeholder="en" onChange={(e) => patch({ language: e.target.value })} />
					</Field>
					<Field id="tg-tpl-mode" label="Formatting">
						<Select value={draft.parse_mode} onValueChange={(v) => patch({ parse_mode: v as ParseMode })}>
							<SelectTrigger id="tg-tpl-mode"><SelectValue /></SelectTrigger>
							<SelectContent>{PARSE_MODES.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent>
						</Select>
					</Field>
					{gateways.length > 0 && (
						<Field id="tg-tpl-gw" label="Available on">
							<Select value={draft.gateway || '__all__'} onValueChange={(v) => patch({ gateway: v === '__all__' ? '' : v })}>
								<SelectTrigger id="tg-tpl-gw"><SelectValue /></SelectTrigger>
								<SelectContent>
									<SelectItem value="__all__">All Telegram bots</SelectItem>
									{gateways.map((g) => <SelectItem key={g} value={g}>{g}</SelectItem>)}
								</SelectContent>
							</Select>
						</Field>
					)}
				</div>
				<Field id="tg-tpl-desc" label="Description (optional)">
					<Input id="tg-tpl-desc" value={draft.description} onChange={(e) => patch({ description: e.target.value })} />
				</Field>

				<Field id="tg-tpl-body" label="Message" error={errors.body} hint={MODE_HELP[draft.parse_mode]}>
					<Textarea id="tg-tpl-body" ref={bodyRef} rows={7} value={draft.body} onChange={(e) => patch({ body: e.target.value })} />
					<div className="flex items-center justify-between">
						<div className="flex items-center gap-2">
							<Input aria-label="New variable name" className="h-8 w-40" placeholder="variable_name" value={newVar} onChange={(e) => setNewVar(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); insertVariable(); } }} />
							<Button type="button" variant="outline" size="sm" disabled={!/^[A-Za-z_][A-Za-z0-9_]*$/.test(newVar.trim())} onClick={insertVariable}><Plus className="mr-1 h-3.5 w-3.5" />Insert variable</Button>
						</div>
						<span className={draft.body.length > limit ? 'text-xs text-danger' : 'text-xs text-steel'}>{draft.body.length} / {limit}</span>
					</div>
				</Field>

				<section className="space-y-2">
					<h3 className="text-sm font-medium text-ink">Media</h3>
					<div className="grid gap-3 sm:grid-cols-[12rem_1fr]">
						<Select value={draft.media_type} onValueChange={(v) => patch({ media_type: v as MediaType, ...(v === 'none' ? { media: '' } : {}) })}>
							<SelectTrigger aria-label="Media type"><SelectValue /></SelectTrigger>
							<SelectContent>{MEDIA_TYPES.map((m) => <SelectItem key={m} value={m}>{mediaTypeLabel(m)}</SelectItem>)}</SelectContent>
						</Select>
						{hasMedia && (
							<div className="flex gap-2">
								<Input aria-label="Media file or link" placeholder="Upload a file or paste a link" value={draft.media} onChange={(e) => patch({ media: e.target.value })} />
								<input ref={fileRef} type="file" hidden accept={ACCEPT[draft.media_type]} onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = ''; }} />
								<Button type="button" variant="outline" onClick={() => fileRef.current?.click()} disabled={uploading}>
									{uploading ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Paperclip className="mr-1 h-4 w-4" />}Upload
								</Button>
							</div>
						)}
					</div>
					{(errors.media || uploadError) && <p role="alert" className="text-xs text-danger">{errors.media || uploadError}</p>}
				</section>

				<section className="space-y-2">
					<h3 className="text-sm font-medium text-ink">Buttons</h3>
					<ButtonsEditor value={draft.buttons_json} onChange={(buttons_json) => patch({ buttons_json })} error={errors.buttons_json} />
				</section>

				<section className="space-y-2">
					<h3 className="text-sm font-medium text-ink">Variables</h3>
					<VariablesTable rows={draft.variables} onChange={(variables) => onChange({ ...draft, variables })} error={errors.variables} />
				</section>

				<label className="flex items-center gap-2 text-sm"><Switch checked={draft.is_active} onCheckedChange={(is_active) => patch({ is_active })} />Active (the agent and welcome messages can use it)</label>
				{errors.form && <p role="alert" className="text-sm text-danger">{errors.form}</p>}

				<div className="flex gap-2">
					<Button type="submit" disabled={saving}>{saving && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}Save template</Button>
					<Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
				</div>
			</form>

			<div className="space-y-3 lg:sticky lg:top-4 lg:self-start">
				<h3 className="text-sm font-medium text-ink">Preview</h3>
				<TemplatePreview draft={draft} values={typed} />
				{draft.variables.length > 0 && (
					<div className="space-y-2">
						<p className="text-xs text-steel">Try values</p>
						{draft.variables.map((v) => (
							<Input key={v.variable} aria-label={`Try ${v.variable}`} placeholder={v.default_value || v.example || v.variable} value={typed[v.variable] ?? ''} onChange={(e) => setTyped({ ...typed, [v.variable]: e.target.value })} />
						))}
					</div>
				)}
			</div>
		</div>
	);
}
