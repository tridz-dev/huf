import { detectVariables, type ParseMode, type TemplateDraft } from '@/services/telegramTemplatesApi';

/** Formatting model for the Telegram-bubble preview. Pure: no React, no network. */

export type FormatNode =
	| { kind: 'text'; value: string }
	| { kind: 'code'; value: string }
	| { kind: 'pre'; value: string }
	| { kind: 'bold' | 'italic' | 'underline' | 'strike' | 'spoiler' | 'quote'; children: FormatNode[] }
	| { kind: 'link'; href: string; children: FormatNode[] };

const t = (value: string): FormatNode => ({ kind: 'text', value });

const ENTITIES: Record<string, string> = { '&lt;': '<', '&gt;': '>', '&amp;': '&', '&quot;': '"' };
const decode = (s: string) => s.replace(/&(lt|gt|amp|quot);/g, (m) => ENTITIES[m] ?? m);

const HTML_TAGS: Record<string, 'bold' | 'italic' | 'underline' | 'strike' | 'spoiler' | 'quote'> = {
	b: 'bold', strong: 'bold', i: 'italic', em: 'italic', u: 'underline', ins: 'underline',
	s: 'strike', strike: 'strike', del: 'strike', 'tg-spoiler': 'spoiler', blockquote: 'quote',
};

interface Frame { tag: string; children: FormatNode[]; make: (children: FormatNode[]) => FormatNode }

const TAG_RE = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s+[^<>]*?)?)\s*>/y;
const flat = (nodes: FormatNode[]): string => nodes.map((n) => (n.kind === 'text' || n.kind === 'code' || n.kind === 'pre' ? n.value : flat(n.children))).join('');

/** Parse the HTML subset Telegram accepts. Unknown or unbalanced tags stay as literal text. */
export function parseTelegramHtml(src: string): FormatNode[] {
	const root: FormatNode[] = [];
	const stack: Frame[] = [];
	const out = () => (stack.length ? stack[stack.length - 1].children : root);
	const pushText = (s: string) => {
		if (!s) return;
		const list = out();
		const last = list[list.length - 1];
		if (last && last.kind === 'text') last.value += s;
		else list.push(t(s));
	};
	let i = 0;
	let buf = '';
	const flush = () => { pushText(decode(buf)); buf = ''; };
	while (i < src.length) {
		if (src[i] === '<') {
			TAG_RE.lastIndex = i;
			const m = TAG_RE.exec(src);
			if (m) {
				const closing = m[1] === '/';
				const tag = m[2].toLowerCase();
				const spoilerSpan = tag === 'span' && /tg-spoiler/.test(m[3]);
				const known = tag in HTML_TAGS || tag === 'a' || tag === 'code' || tag === 'pre' || spoilerSpan;
				if (known && !closing) {
					flush();
					const href = decode(/href\s*=\s*"([^"]*)"/.exec(m[3])?.[1] ?? '');
					const make = (children: FormatNode[]): FormatNode =>
						tag === 'a' ? { kind: 'link', href, children }
						: tag === 'code' ? { kind: 'code', value: flat(children) }
						: tag === 'pre' ? { kind: 'pre', value: flat(children) }
						: { kind: spoilerSpan ? 'spoiler' : HTML_TAGS[tag], children };
					stack.push({ tag, children: [], make });
					i += m[0].length;
					continue;
				}
				if (known && closing && stack.length && stack[stack.length - 1].tag === tag) {
					flush();
					const frame = stack.pop()!;
					out().push(frame.make(frame.children));
					i += m[0].length;
					continue;
				}
			}
		}
		buf += src[i];
		i += 1;
	}
	flush();
	// Unclosed tags: re-emit as literal text.
	while (stack.length) {
		const frame = stack.pop()!;
		out().push(t(`<${frame.tag}>`), ...frame.children);
	}
	return root;
}

const MDV2_SPECIAL = new Set('_*[]()~`>#+-=|{}.!\\'.split(''));

/** Parse MarkdownV2. Unclosed markers stay literal; a backslash escapes any special character. */
export function parseMarkdownV2(src: string): FormatNode[] {
	function run(from: number, closer: string | null): { nodes: FormatNode[]; end: number; closed: boolean } {
		const nodes: FormatNode[] = [];
		let buf = '';
		let i = from;
		const flush = () => { if (buf) { nodes.push(t(buf)); buf = ''; } };
		while (i < src.length) {
			const c = src[i];
			if (c === '\\' && i + 1 < src.length && MDV2_SPECIAL.has(src[i + 1])) { buf += src[i + 1]; i += 2; continue; }
			if (closer && src.startsWith(closer, i) && (closer.length > 1 || src[i + 1] !== '_' || closer !== '_')) {
				flush();
				return { nodes, end: i + closer.length, closed: true };
			}
			if (src.startsWith('```', i)) {
				const end = src.indexOf('```', i + 3);
				if (end > 0) {
					flush();
					const body = src.slice(i + 3, end).replace(/^[A-Za-z0-9+#-]*\n/, '');
					nodes.push({ kind: 'pre', value: body });
					i = end + 3;
					continue;
				}
			}
			if (c === '`') {
				const end = src.indexOf('`', i + 1);
				if (end > 0) { flush(); nodes.push({ kind: 'code', value: src.slice(i + 1, end) }); i = end + 1; continue; }
			}
			const marker = src.startsWith('__', i) ? '__' : src.startsWith('||', i) ? '||' : c === '*' || c === '_' || c === '~' ? c : '';
			const kinds: Record<string, 'bold' | 'italic' | 'underline' | 'strike' | 'spoiler'> = {
				'*': 'bold', _: 'italic', __: 'underline', '~': 'strike', '||': 'spoiler',
			};
			if (marker) {
				const inner = run(i + marker.length, marker);
				if (inner.closed && inner.nodes.length) {
					flush();
					nodes.push({ kind: kinds[marker], children: inner.nodes });
					i = inner.end;
					continue;
				}
			}
			if (c === '[') {
				const m = /^\[([^\]]+)\]\(([^)\s]+)\)/.exec(src.slice(i));
				if (m) { flush(); nodes.push({ kind: 'link', href: m[2], children: [t(m[1])] }); i += m[0].length; continue; }
			}
			if (c === '>' && (i === 0 || src[i - 1] === '\n')) {
				const eol = src.indexOf('\n', i);
				const line = src.slice(i + 1, eol < 0 ? undefined : eol);
				flush();
				nodes.push({ kind: 'quote', children: [t(line.replace(/^ /, ''))] });
				i = eol < 0 ? src.length : eol + 1;
				continue;
			}
			buf += c;
			i += 1;
		}
		flush();
		return { nodes, end: i, closed: false };
	}
	return run(0, null).nodes;
}

export function parseFormatted(src: string, mode: ParseMode): FormatNode[] {
	if (mode === 'HTML') return parseTelegramHtml(src);
	if (mode === 'MarkdownV2') return parseMarkdownV2(src);
	return src ? [t(src)] : [];
}

const escapeHtml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const escapeMd = (s: string) => s.replace(/([_*[\]()~`>#+\-=|{}.!\\])/g, '\\$1');

/** Substitute {{var}} with an (escaped) value; variables without a value are listed in `missing`. */
export function substituteVariables(src: string, values: Record<string, string>, mode: ParseMode): { text: string; missing: string[] } {
	const missing: string[] = [];
	const esc = mode === 'HTML' ? escapeHtml : mode === 'MarkdownV2' ? escapeMd : (s: string) => s;
	const text = src.replace(/\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g, (whole, name: string) => {
		const v = values[name];
		if (v) return esc(v);
		if (!missing.includes(name)) missing.push(name);
		return whole;
	});
	return { text, missing };
}

/** Preview values: typed sample, else the variable's default, else its example. */
export function sampleValues(draft: Pick<TemplateDraft, 'variables'>, typed: Record<string, string>): Record<string, string> {
	const out: Record<string, string> = {};
	for (const v of draft.variables) out[v.variable] = typed[v.variable] || v.default_value || v.example || '';
	return out;
}

// -- buttons ------------------------------------------------------------------------------------

export const BUTTON_KINDS = ['callback', 'url', 'web_app', 'switch_inline', 'copy_text', 'login_url'] as const;
export type ButtonKind = (typeof BUTTON_KINDS)[number];
export const MAX_PER_ROW = 8;
export const MAX_ROWS = 10;
export const MAX_BUTTONS = 40;

export interface EditorButton { text: string; kind: ButtonKind; value: string }
export interface ButtonsModel { rows: EditorButton[][]; once: boolean; edit: boolean }

export const emptyButtons = (): ButtonsModel => ({ rows: [], once: false, edit: false });

/** Parse buttons_json into the editor model; `null` when it is not an inline-keyboard spec we can edit. */
export function parseButtons(json: string): ButtonsModel | null {
	if (!json.trim()) return emptyButtons();
	let raw: unknown;
	try { raw = JSON.parse(json); } catch { return null; }
	if (!raw || typeof raw !== 'object') return null;
	const spec = raw as { rows?: unknown; once?: unknown; edit?: unknown };
	if (!Array.isArray(spec.rows)) return null;
	const rows: EditorButton[][] = [];
	for (const row of spec.rows) {
		if (!Array.isArray(row)) return null;
		const out: EditorButton[] = [];
		for (const b of row as Record<string, unknown>[]) {
			const kind = BUTTON_KINDS.find((k) => b?.[k] !== undefined && b?.[k] !== '');
			if (!kind) { out.push({ text: String(b?.text ?? ''), kind: 'callback', value: '' }); continue; }
			out.push({ text: String(b.text ?? ''), kind, value: String(b[kind]) });
		}
		rows.push(out);
	}
	return { rows, once: Boolean(spec.once), edit: Boolean(spec.edit) };
}

/** The telegram-buttons JSON for the model; empty string when there are no buttons. */
export function buttonsToJson(model: ButtonsModel): string {
	const rows = model.rows.filter((r) => r.length).map((r) => r.map((b) => ({ text: b.text, [b.kind]: b.value })));
	if (!rows.length) return '';
	const spec: Record<string, unknown> = { rows };
	if (model.edit) spec.edit = true;
	if (model.once) spec.once = true;
	return JSON.stringify(spec);
}

export function validateButtons(model: ButtonsModel): string[] {
	const errors: string[] = [];
	const rows = model.rows.filter((r) => r.length);
	if (rows.length > MAX_ROWS) errors.push(`At most ${MAX_ROWS} rows.`);
	if (rows.reduce((n, r) => n + r.length, 0) > MAX_BUTTONS) errors.push(`At most ${MAX_BUTTONS} buttons.`);
	rows.forEach((r, ri) => {
		if (r.length > MAX_PER_ROW) errors.push(`Row ${ri + 1} has more than ${MAX_PER_ROW} buttons.`);
		r.forEach((b, bi) => {
			const label = `Row ${ri + 1}, button ${bi + 1}`;
			const v = b.value.trim();
			if (!b.text.trim()) errors.push(`${label}: add a label.`);
			if (!v) errors.push(`${label}: add a ${b.kind === 'callback' ? 'button id' : 'value'}.`);
			else if (b.kind === 'callback' && new TextEncoder().encode(v).length > 46) errors.push(`${label}: the id is too long (46 bytes max).`);
			else if ((b.kind === 'web_app' || b.kind === 'login_url') && !/^https:\/\//i.test(v) && !/\{\{/.test(v)) errors.push(`${label}: use an https link.`);
			else if (b.kind === 'url' && !/^(https?:\/\/|tg:\/\/)/i.test(v) && !/\{\{/.test(v)) errors.push(`${label}: use a http(s) or tg:// link.`);
			else if (b.kind === 'copy_text' && v.length > 256) errors.push(`${label}: copy text is limited to 256 characters.`);
		});
	});
	return errors;
}

// -- the whole bubble --------------------------------------------------------------------------

export interface BubbleModel {
	media: { type: string; url: string } | null;
	nodes: FormatNode[];
	rows: { text: string; kind: ButtonKind }[][];
	missing: string[];
	overLimit: boolean;
}

export function buildBubble(draft: TemplateDraft, typed: Record<string, string> = {}): BubbleModel {
	const values = sampleValues(draft, typed);
	const { text, missing } = substituteVariables(draft.body, values, draft.parse_mode);
	const buttons = parseButtons(draft.buttons_json);
	const mediaOn = draft.media_type !== 'none' && Boolean(draft.media.trim());
	const limit = mediaOn && draft.media_type !== 'sticker' ? 1024 : 4096;
	return {
		media: mediaOn ? { type: draft.media_type, url: draft.media.trim() } : null,
		nodes: parseFormatted(text, draft.parse_mode),
		rows: (buttons?.rows ?? []).filter((r) => r.length).map((r) => r.map((b) => ({ text: substituteVariables(b.text, values, 'Plain').text, kind: b.kind }))),
		missing: [...new Set([...missing, ...detectVariables(draft.buttons_json).filter((v) => !values[v])])],
		overLimit: draft.body.length > limit,
	};
}
