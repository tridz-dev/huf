/**
 * Fields found in one example (a webhook sample pasted or received, kept on the trigger as `sample`). The server does the
 * same for saved flows (`huf/ai/flow/catalog/fields.py`); this copy lets the picker react to an example the person has
 * just added, before it is saved. Same rules: depth 3, 40 fields, `_` keys hidden, keys that are not a plain name are
 * "advanced only", objects and lists get one short sentence instead of their content.
 */
import { friendlyDate, humanizeSentence, isIsoDate } from '../flow-run/humanize';
import type { CatalogField, FieldType, ListInfo } from './types';

export const MAX_FIELDS = 40;
const MAX_DEPTH = 3;
const MAX_ITEM_FIELDS = 12;
const IDENT = /^[A-Za-z_][A-Za-z0-9_]*$/;
const ACRONYMS: Record<string, string> = { id: 'ID', url: 'URL', sku: 'SKU', api: 'API', sms: 'SMS', ip: 'IP', pdf: 'PDF', gst: 'GST', vat: 'VAT', crm: 'CRM', csv: 'CSV', po: 'PO', otp: 'OTP' };

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

/** "customer_name" -> "Customer name", "orderID" -> "Order ID". */
export function sentenceLabel(key: string): string {
  const words = key.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[_\-.]+/g, ' ').trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return key;
  return words.map((w, i) => ACRONYMS[w.toLowerCase()] ?? (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1).toLowerCase() : w.toLowerCase())).join(' ');
}

export function fieldType(value: unknown): FieldType {
  if (typeof value === 'boolean') return 'yes_no';
  if (typeof value === 'number') return 'number';
  if (Array.isArray(value)) return 'list';
  if (isObj(value)) return 'object';
  if (typeof value === 'string' && isIsoDate(value)) return 'date';
  return 'text';
}

function clip(text: string, n = 80): string {
  const t = text.replace(/\s+/g, ' ').trim();
  return t.length <= n ? t : `${t.slice(0, n - 1).trimEnd()}…`;
}

const HEADLINE_KEYS = ['name', 'full_name', 'customer_name', 'title', 'subject', 'label', 'display_name', 'email'];

/** The short name of a record ("Ada Lovelace"), the same keys the server uses. */
function headline(obj: Record<string, unknown>): string | null {
  const key = HEADLINE_KEYS.find((k) => typeof obj[k] === 'string' && (obj[k] as string).trim());
  return key ? (obj[key] as string).trim() : null;
}

export function sampleOf(value: unknown): CatalogField['sample'] {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'boolean' || typeof value === 'number') return value;
  if (typeof value === 'string') return clip(value);
  const sentence = isObj(value) ? headline(value) ?? humanizeSentence(value) : humanizeSentence(value);
  return sentence ? clip(sentence) : null;
}

function listInfo(items: unknown[]): ListInfo {
  const first = items.find((i) => i !== null && i !== undefined);
  return {
    count: items.length,
    item_type: first === undefined ? 'text' : fieldType(first),
    item_texts: items.slice(0, 5).map((i) => sampleOf(i)).filter((t): t is string | number | boolean => t !== null).map(String),
    item_fields: isObj(first) ? walk(first, '', 0, [], MAX_ITEM_FIELDS, false) : [],
  };
}

function walk(obj: Record<string, unknown>, prefix: string, depth: number, trail: string[], budget: number, withLists = true): CatalogField[] {
  const out: CatalogField[] = [];
  for (const [key, value] of Object.entries(obj)) {
    if (out.length >= budget) break;
    if (key.startsWith('_')) continue;
    const parts = [...trail, sentenceLabel(key)];
    const type = fieldType(value);
    const field: CatalogField = { path: IDENT.test(key) ? (prefix ? `${prefix}.${key}` : key) : null, label: parts.join(' > '), type, sample: sampleOf(value) };
    if (field.path === null) {
      out.push({ ...field, advanced_only: true });
      continue;
    }
    if (type === 'list' && withLists) field.list = listInfo(value as unknown[]);
    out.push(field);
    if (type === 'object' && depth + 1 < MAX_DEPTH && budget - out.length > 0) out.push(...walk(value as Record<string, unknown>, field.path, depth + 1, parts, budget - out.length, withLists));
  }
  return out.slice(0, budget);
}

export function inferFields(sample: unknown, root: string, rootLabel = 'Result'): CatalogField[] {
  if (isObj(sample)) return walk(sample, root, 0, [], MAX_FIELDS);
  if (sample === null || sample === undefined || sample === '') return [];
  const type = fieldType(sample);
  return [{ path: root, label: rootLabel, type, sample: sampleOf(sample), ...(type === 'list' ? { list: listInfo(sample as unknown[]) } : {}) }];
}

/** An example value as people read it. */
export function sampleText(sample: CatalogField['sample'], type: FieldType): string {
  if (sample === null || sample === undefined || sample === '') return '';
  if (typeof sample === 'boolean') return sample ? 'Yes' : 'No';
  if (typeof sample === 'number') return String(sample);
  return type === 'date' ? friendlyDate(sample) : sample;
}
