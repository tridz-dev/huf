import { call, file } from '@/lib/frappe-sdk';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { unwrap, type Result } from '@/services/telegramApi';

/** Typed client for the Telegram templates tab (huf/ai/telegram_management_templates.py). */
const BASE = 'huf.ai.telegram_management_templates';

export const PARSE_MODES = ['HTML', 'MarkdownV2', 'Plain'] as const;
export type ParseMode = (typeof PARSE_MODES)[number];
export const MEDIA_TYPES = ['none', 'photo', 'video', 'animation', 'document', 'audio', 'voice', 'sticker'] as const;
export type MediaType = (typeof MEDIA_TYPES)[number];
export const TEXT_LIMIT = 4096;
export const CAPTION_LIMIT = 1024;
export const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 _-]{0,79}$/;
const VAR_RE = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g;

export interface TemplateVariable {
	variable: string;
	default_value: string;
	example: string;
}

export interface TemplateSummary {
	name: string;
	template_name: string;
	gateway: string | null;
	language: string | null;
	parse_mode: ParseMode;
	media_type: MediaType;
	is_active: 0 | 1 | boolean;
	description: string | null;
	last_used_at: string | null;
	modified: string;
}

/** The editable template (what save_template accepts and get_template returns). */
export interface TemplateDraft {
	name?: string;
	template_name: string;
	gateway: string;
	language: string;
	parse_mode: ParseMode;
	body: string;
	media_type: MediaType;
	media: string;
	buttons_json: string;
	is_active: boolean;
	description: string;
	variables: TemplateVariable[];
}

export interface FieldProblem {
	field: string;
	message: string;
}

export interface PreviewResult {
	text: string;
	parse_mode: string;
	media: { type: string; source: string; value: string } | null;
	markup?: unknown;
	missing: string[];
	errors: string[];
}

/** Variable names used in the texts, in first-seen order. */
export function detectVariables(...texts: (string | null | undefined)[]): string[] {
	const seen: string[] = [];
	for (const text of texts) {
		for (const m of (text ?? '').matchAll(VAR_RE)) if (!seen.includes(m[1])) seen.push(m[1]);
	}
	return seen;
}

/** Keep the variables table in step with the text: one row per used variable, existing values preserved. */
export function syncVariables(rows: TemplateVariable[], body: string, buttonsJson: string): TemplateVariable[] {
	const byName = new Map(rows.map((r) => [r.variable, r]));
	return detectVariables(body, buttonsJson).map((v) => byName.get(v) ?? { variable: v, default_value: '', example: '' });
}

export function emptyDraft(gateway = ''): TemplateDraft {
	return {
		template_name: '', gateway, language: 'en', parse_mode: 'HTML', body: '', media_type: 'none', media: '',
		buttons_json: '', is_active: true, description: '', variables: [],
	};
}

type Raw = Partial<Omit<TemplateDraft, 'is_active' | 'variables'>> & {
	name?: string; is_active?: unknown; variables?: Partial<TemplateVariable>[] | null;
};

export function rowToDraft(raw: Raw): TemplateDraft {
	const base = emptyDraft();
	return {
		name: raw.name,
		template_name: raw.template_name ?? '',
		gateway: raw.gateway ?? '',
		language: raw.language ?? base.language,
		parse_mode: (PARSE_MODES as readonly string[]).includes(raw.parse_mode ?? '') ? (raw.parse_mode as ParseMode) : 'HTML',
		body: raw.body ?? '',
		media_type: (MEDIA_TYPES as readonly string[]).includes(raw.media_type ?? '') ? (raw.media_type as MediaType) : 'none',
		media: raw.media ?? '',
		buttons_json: raw.buttons_json ?? '',
		is_active: raw.is_active === undefined ? true : Boolean(Number(raw.is_active)),
		description: raw.description ?? '',
		variables: (raw.variables ?? []).map((v) => ({
			variable: v.variable ?? '', default_value: v.default_value ?? '', example: v.example ?? '',
		})),
	};
}

/** Payload for save_template. Empty optional fields become null so the doctype keeps them unset. */
export function draftToValues(d: TemplateDraft): Record<string, unknown> {
	const mediaOn = d.media_type !== 'none';
	return {
		template_name: d.template_name.trim(),
		gateway: d.gateway || null,
		language: d.language.trim() || null,
		parse_mode: d.parse_mode,
		body: d.body,
		media_type: d.media_type,
		media: mediaOn ? d.media.trim() : null,
		buttons_json: d.buttons_json.trim() || null,
		is_active: d.is_active ? 1 : 0,
		description: d.description.trim() || null,
		variables: d.variables.map((v) => ({ variable: v.variable, default_value: v.default_value, example: v.example })),
	};
}

/** Client-side checks mirroring the server, so most problems show before a round trip. */
export function validateDraft(d: TemplateDraft): FieldProblem[] {
	const out: FieldProblem[] = [];
	const name = d.template_name.trim();
	if (!name) out.push({ field: 'template_name', message: 'Give the template a name.' });
	else if (!NAME_RE.test(name)) out.push({ field: 'template_name', message: 'Use letters, numbers, spaces, dashes and underscores (max 80).' });
	const withMedia = d.media_type !== 'none';
	if (withMedia && !d.media.trim()) out.push({ field: 'media', message: 'Attach a file or enter a link for the media.' });
	if (!withMedia && !d.body.trim()) out.push({ field: 'body', message: 'Write the message text.' });
	const limit = withMedia && d.media_type !== 'sticker' ? CAPTION_LIMIT : TEXT_LIMIT;
	if (d.body.length > limit) {
		out.push({ field: 'body', message: withMedia ? `With media the text is a caption (max ${CAPTION_LIMIT} characters).` : `Telegram allows at most ${TEXT_LIMIT} characters.` });
	}
	if (d.buttons_json.trim()) {
		try {
			const parsed = JSON.parse(d.buttons_json);
			if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error();
		} catch {
			out.push({ field: 'buttons_json', message: 'Buttons must be valid JSON.' });
		}
	}
	return out;
}

/** Server `problems` -> map of field to first message (variables.N collapse to "variables"). */
export function problemsByField(problems: FieldProblem[]): Record<string, string> {
	const map: Record<string, string> = {};
	for (const p of problems) {
		const key = p.field.startsWith('variables') ? 'variables' : p.field;
		if (!(key in map)) map[key] = p.message;
	}
	return map;
}

export interface SaveFailure { error: string; problems: FieldProblem[] }
export type SaveResult = { ok: true; template: TemplateDraft } | ({ ok: false } & SaveFailure);

async function request<T>(method: string, args: Record<string, unknown>, verb: 'get' | 'post' = 'get'): Promise<Result<T>> {
	try {
		return unwrap<T>(await (verb === 'get' ? call.get : call.post)(`${BASE}.${method}`, args));
	} catch (e) {
		return { ok: false, error: getFrappeErrorMessage(e) };
	}
}

export async function listTemplates(gateway?: string): Promise<Result<TemplateSummary[]>> {
	const res = await request<{ templates: TemplateSummary[] }>('list_templates', gateway ? { gateway } : {});
	return res.ok ? { ok: true, data: res.data.templates ?? [] } : res;
}

export async function getTemplate(name: string): Promise<Result<TemplateDraft>> {
	const res = await request<{ template: Raw }>('get_template', { name });
	return res.ok ? { ok: true, data: rowToDraft(res.data.template) } : res;
}

export async function saveTemplate(draft: TemplateDraft): Promise<SaveResult> {
	const args: Record<string, unknown> = { values: draftToValues(draft) };
	if (draft.name) args.name = draft.name;
	try {
		const res = (await call.post(`${BASE}.save_template`, args)) as { message?: Record<string, unknown> };
		const body = (res?.message ?? res ?? {}) as { success?: boolean; template?: Raw; error?: string; message?: string; problems?: FieldProblem[] };
		if (body.success === false) {
			return { ok: false, error: body.message || body.error || 'Could not save', problems: body.problems ?? [] };
		}
		return { ok: true, template: rowToDraft(body.template ?? {}) };
	} catch (e) {
		return { ok: false, error: getFrappeErrorMessage(e), problems: [] };
	}
}

export async function deleteTemplate(name: string): Promise<Result<unknown>> {
	return request('delete_template', { name }, 'post');
}

/** Saved template by name, or unsaved editor values. */
export async function previewTemplate(target: string | TemplateDraft, variables: Record<string, string>, gateway?: string): Promise<Result<PreviewResult>> {
	const res = await request<{ preview: PreviewResult }>(
		'preview_template',
		{ name_or_values: typeof target === 'string' ? target : draftToValues(target), variables, ...(gateway ? { gateway } : {}) },
		'post',
	);
	return res.ok ? { ok: true, data: res.data.preview } : res;
}

export async function sendTestTemplate(args: { gateway: string; chatId: string; name: string; variables: Record<string, string> }): Promise<Result<unknown>> {
	return request('send_test_template', { gateway: args.gateway, chat_id: args.chatId.trim(), name: args.name, variables: args.variables, confirm: 1 }, 'post');
}

/** Upload a public file (Telegram fetches by URL or the server reads it) and return its server path. */
export async function uploadTemplateMedia(f: File): Promise<Result<{ fileUrl: string }>> {
	try {
		const res = await file.uploadFile(f, { isPrivate: false });
		const data = (res as { data?: { message?: { file_url?: string }; file_url?: string } }).data;
		const fileUrl = data?.message?.file_url || data?.file_url;
		return fileUrl ? { ok: true, data: { fileUrl } } : { ok: false, error: 'The upload did not return a file.' };
	} catch (e) {
		return { ok: false, error: getFrappeErrorMessage(e) };
	}
}

const MEDIA_LABEL: Record<MediaType, string> = {
	none: 'No media', photo: 'Photo', video: 'Video', animation: 'GIF / animation', document: 'Document',
	audio: 'Audio', voice: 'Voice message', sticker: 'Sticker',
};
export const mediaTypeLabel = (t: MediaType) => MEDIA_LABEL[t] ?? t;

export function filterTemplates(rows: TemplateSummary[], search: string): TemplateSummary[] {
	const q = search.trim().toLowerCase();
	if (!q) return rows;
	return rows.filter((r) => `${r.template_name} ${r.description ?? ''} ${r.language ?? ''}`.toLowerCase().includes(q));
}
