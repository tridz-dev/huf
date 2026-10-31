import type { GatewayPayloadField, GatewayPayloadType, GatewayTriggerSpec } from '../flow-gateway/gatewayTrigger.types';
import { sampleOf } from './infer';
import type { CatalogField, FieldType } from './types';

/**
 * The "Use data from" entries of a chat trigger, from the server registry: friendly names (Sender name, Message text,
 * Button chosen), the example of the last real message when the trigger has one, else the registry's sample. Ids stay
 * out of sight (`advanced_only`), so nobody sees a sender id, a conversation id or the message record.
 */
const TYPE: Record<GatewayPayloadType, FieldType> = { text: 'text', number: 'number', yes_no: 'yes_no', list: 'list', datetime: 'date', record: 'text' };

const fieldName = (path: string) => path.replace(/^input\./, '');

function toField(f: GatewayPayloadField, example: Record<string, unknown> | undefined): CatalogField {
  const name = fieldName(f.path);
  const value = example && name in example ? example[name] : f.sample;
  const type = TYPE[f.type] ?? 'text';
  const out: CatalogField = { path: f.path, label: f.label, type };
  if (type === 'list') {
    const items = Array.isArray(value) ? value : [];
    out.list = { count: items.length, item_type: 'text', item_texts: items.slice(0, 5).map((i) => String(sampleOf(i) ?? '')).filter(Boolean), item_fields: [] };
  } else {
    out.sample = sampleOf(value);
  }
  if (f.advanced) out.advanced_only = true;
  if (f.customer_provided) out.untrusted = true;
  return out;
}

/** Fields offered for a chat trigger. `example` is the trigger's pinned/last real message (`input` keys), if any. */
export function gatewayPickerFields(spec: GatewayTriggerSpec, example?: Record<string, unknown>): CatalogField[] {
  return spec.payload_fields.map((f) => toField(f, example));
}
