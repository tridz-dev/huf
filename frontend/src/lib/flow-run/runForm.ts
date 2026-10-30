/**
 * The Run dialog's form: the fields a flow's trigger declares (`contract.input_schema`) or, failing that, the fields of
 * the Webhook trigger's saved sample request (`node._sample`), turned into labelled inputs and back into the payload.
 *
 * Pure functions. Anything the form does not show (lists, deep objects) is carried over untouched from the starting
 * data, so "Use sample" never loses part of the sample.
 */
import { labelFor } from './humanize';

export type RunFieldKind = 'text' | 'number' | 'yesno' | 'longtext';

export interface RunField {
  /** Path inside the payload: ['address', 'city']. */
  path: string[];
  /** Stable id: "address.city". */
  id: string;
  /** "Address > City" or the schema's own title. */
  label: string;
  kind: RunFieldKind;
  /** The value the sample / schema example holds, as shown in the box. */
  example: string | boolean;
}

export type RunFormValues = Record<string, string | boolean>;

const MAX_FIELDS = 12;
const MAX_DEPTH = 2;
const LONG = 80;
const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

const kindOf = (value: unknown, schemaType?: string): RunFieldKind => {
  if (typeof value === 'boolean' || schemaType === 'boolean') return 'yesno';
  if (typeof value === 'number' || schemaType === 'integer' || schemaType === 'number') return 'number';
  if (typeof value === 'string' && (value.length > LONG || value.includes('\n'))) return 'longtext';
  return 'text';
};

const show = (value: unknown): string | boolean => {
  if (typeof value === 'boolean') return value;
  if (value === null || value === undefined) return '';
  return String(value);
};

function fromSample(sample: Record<string, unknown>, parent: string[], depth: number, labelPrefix: string, out: RunField[]): void {
  for (const [key, value] of Object.entries(sample)) {
    if (out.length >= MAX_FIELDS) return;
    if (key.startsWith('_')) continue;
    const path = [...parent, key];
    const label = `${labelPrefix}${labelFor(key)}`;
    if (isObj(value)) {
      if (depth < MAX_DEPTH) fromSample(value, path, depth + 1, `${label} > `, out);
      continue;
    }
    if (Array.isArray(value)) continue; // carried over, not edited here
    out.push({ path, id: path.join('.'), label, kind: kindOf(value), example: show(value) });
  }
}

/** The fields a sample request offers, in the order it lists them. */
export function fieldsFromSample(sample: unknown): RunField[] {
  const out: RunField[] = [];
  if (isObj(sample)) fromSample(sample, [], 0, '', out);
  return out;
}

function fromSchema(schema: Record<string, unknown>, parent: string[], depth: number, labelPrefix: string, out: RunField[]): void {
  const props = isObj(schema.properties) ? schema.properties : {};
  for (const [key, raw] of Object.entries(props)) {
    if (out.length >= MAX_FIELDS) return;
    const prop = isObj(raw) ? raw : {};
    const path = [...parent, key];
    const label = `${labelPrefix}${labelFor(key, typeof prop.title === 'string' ? prop.title : null)}`;
    const type = typeof prop.type === 'string' ? prop.type : undefined;
    if (type === 'object' && depth < MAX_DEPTH) {
      fromSchema(prop, path, depth + 1, `${label} > `, out);
      continue;
    }
    if (type === 'array' || type === 'object') continue;
    const example = prop.example ?? (Array.isArray(prop.examples) ? prop.examples[0] : undefined) ?? prop.default;
    const kind = kindOf(example, type);
    out.push({ path, id: path.join('.'), label, kind, example: kind === 'yesno' ? example === true : show(example) });
  }
}

/** The fields a JSON-Schema input declares (`properties`, optional `title` / `example` per property). */
export function fieldsFromSchema(schema: unknown): RunField[] {
  const out: RunField[] = [];
  if (isObj(schema)) fromSchema(schema, [], 0, '', out);
  return out;
}

/** What the form shows: the declared fields when there are any, else the sample's. */
export function runFormFields(inputSchema: unknown, sample: unknown): RunField[] {
  const declared = fieldsFromSchema(inputSchema);
  return declared.length > 0 ? declared : fieldsFromSample(sample);
}

const getAt = (data: unknown, path: string[]): unknown => path.reduce<unknown>((cur, key) => (isObj(cur) ? cur[key] : undefined), data);

/** Starting values for the boxes from a payload (a sample, the last real request or the last run). */
export function valuesFromPayload(fields: RunField[], payload: unknown): RunFormValues {
  const values: RunFormValues = {};
  for (const f of fields) {
    const found = getAt(payload, f.path);
    values[f.id] = found === undefined ? (f.kind === 'yesno' ? false : '') : show(found);
  }
  return values;
}

const clone = <T,>(v: T): T => (v === undefined ? v : (JSON.parse(JSON.stringify(v)) as T));

function setAt(target: Record<string, unknown>, path: string[], value: unknown): void {
  let cur = target;
  path.slice(0, -1).forEach((key) => {
    if (!isObj(cur[key])) cur[key] = {};
    cur = cur[key] as Record<string, unknown>;
  });
  cur[path[path.length - 1]] = value;
}

function removeAt(target: Record<string, unknown>, path: string[]): void {
  const parent = path.length > 1 ? getAt(target, path.slice(0, -1)) : target;
  if (isObj(parent)) delete parent[path[path.length - 1]];
}

/** The payload for the form's values: `base` (kept as it is) with every shown field set from its box. An empty box leaves the field out. */
export function payloadFromForm(base: unknown, fields: RunField[], values: RunFormValues): Record<string, unknown> {
  const out: Record<string, unknown> = isObj(base) ? clone(base) : {};
  for (const f of fields) {
    const raw = values[f.id];
    if (f.kind === 'yesno') {
      setAt(out, f.path, raw === true);
      continue;
    }
    const text = typeof raw === 'string' ? raw.trim() : '';
    if (text === '') {
      removeAt(out, f.path);
    } else if (f.kind === 'number' && /^-?\d+(\.\d+)?$/.test(text)) {
      setAt(out, f.path, Number(text));
    } else {
      setAt(out, f.path, typeof raw === 'string' ? raw : text);
    }
  }
  return out;
}

/** True when the payload has something in it. */
export const hasData = (payload: unknown): boolean => isObj(payload) && Object.keys(payload).length > 0;
