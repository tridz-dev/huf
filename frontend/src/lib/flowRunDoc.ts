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
  'parent', 'parentfield', 'parenttype', 'amended_from', 'naming_series', '_user_tags', '_comments', '_assign', '_liked_by', '__unsaved',
]);

export interface DocSummary {
  doctype: string;
  name: string;
  /** "Created", "Submitted"... or null when the event is not known. */
  event: string | null;
  fields: Array<{ key: string; label: string; value: string }>;
  /** Number of fields not shown (empty ones and tables are left out). */
  hidden: number;
}

const prettyKey = (key: string): string => {
  const words = key.replace(/_/g, ' ').trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : key;
};

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
    shown.push({ key, label: prettyKey(key), value: typeof value === 'boolean' ? (value ? 'Yes' : 'No') : shorten(String(value)) });
  }
  return { doctype: o.doctype, name: o.name, event: event ? DOC_EVENT_WORDS[event] ?? null : null, fields: shown, hidden };
}
