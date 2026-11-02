/**
 * Plain summary of the document a Data trigger run was started for. The trigger input is the whole document as
 * the server stores it, with bookkeeping fields (owner, docstatus, idx...) that mean nothing to a flow author.
 */

const DOC_EVENT_WORDS: Record<string, string> = {
  after_insert: 'Created',
  on_update: 'Updated',
  on_submit: 'Submitted',
  on_cancel: 'Cancelled',
  on_trash: 'Deleted',
};

/** Fields the server adds to every document that are not part of what the user entered. */
const INTERNAL_KEYS = new Set([
  'doctype', 'name', 'owner', 'creation', 'modified', 'modified_by', 'docstatus', 'idx',
  'parent', 'parentfield', 'parenttype', 'amended_from', 'naming_series', '_trigger', '_user_tags', '_comments', '_assign', '_liked_by', '__unsaved',
]);

export interface DocSummary {
  doctype: string;
  name: string;
  /** "Created", "Submitted"... or null when the event is not known. */
  event: string | null;
  /** `full` is set when `value` was cut short, so the page can offer "Show more". */
  fields: Array<{ key: string; label: string; value: string; full?: string }>;
  /** Number of fields not shown (empty ones and tables are left out). */
  hidden: number;
}

/** Desk URL of a document, so the run page can link to it. */
export const deskDocUrl = (doctype: string, name: string): string =>
  `/app/${doctype.toLowerCase().replace(/[\s_]+/g, '-')}/${encodeURIComponent(name)}`;

const prettyKey = (key: string): string => {
  const words = key.replace(/_/g, ' ').trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : key;
};

const HTML_HINT = /<\/?[a-z][^>]*>|&(?:[a-z]+|#\d+|#x[0-9a-f]+);/i;

/** Rich-text field values (ToDo description...) arrive as HTML: plain text with line breaks kept. */
export function htmlToText(value: string): string {
  if (!HTML_HINT.test(value)) return value;
  const spaced = value.replace(/<br\s*\/?>|<\/(p|div|li|h[1-6]|tr)>/gi, '\n');
  let text: string;
  if (typeof DOMParser !== 'undefined') {
    text = new DOMParser().parseFromString(spaced, 'text/html').body.textContent ?? '';
  } else {
    text = spaced.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
  }
  return text.replace(/\u00a0/g, ' ').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}

const shorten = (text: string, max = 120): string => (text.length > max ? `${text.slice(0, max - 1)}…` : text);

/** Summary of a trigger input that is a document (has a doctype and a name); null for any other input. */
export function summarizeDocPayload(input: unknown, event?: string | null, maxFields = 8): DocSummary | null {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return null;
  const o = input as Record<string, unknown>;
  if (typeof o.doctype !== 'string' || !o.doctype || typeof o.name !== 'string' || !o.name) return null;
  const shown: DocSummary['fields'] = [];
  let hidden = 0;
  for (const [key, value] of Object.entries(o)) {
    if (INTERNAL_KEYS.has(key)) continue;
    const scalar = typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean';
    if (!scalar || value === '' || value === null) {
      hidden += 1;
      continue;
    }
    if (shown.length >= maxFields) {
      hidden += 1;
      continue;
    }
    const text = typeof value === 'boolean' ? (value ? 'Yes' : 'No') : htmlToText(String(value));
    const short = shorten(text);
    shown.push(short === text ? { key, label: prettyKey(key), value: text } : { key, label: prettyKey(key), value: short, full: text });
  }
  const fired = o._trigger && typeof o._trigger === 'object' ? (o._trigger as Record<string, unknown>).event : null;
  const eventKey = event || (typeof fired === 'string' ? fired : null);
  return { doctype: o.doctype, name: o.name, event: eventKey ? DOC_EVENT_WORDS[eventKey] ?? null : null, fields: shown, hidden };
}
