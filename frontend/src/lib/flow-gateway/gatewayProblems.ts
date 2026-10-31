import type { GatewayChoice, GatewayParam, GatewayParamSpec, GatewayRegistry, GatewayTriggerSpec } from './gatewayTrigger.types';
import { GATEWAY_TRIGGER_KINDS } from './triggerKinds';
import { channelNoun, gatewaysForKind, pickPrompt, type GatewayKindId } from './gatewayWords';

export interface GatewayIssue {
  /** `gateway`, or `params.<key>` for a filter. */
  field: string;
  message: string;
}

type Limits = GatewayRegistry['limits'];
const DEFAULT_LIMITS: Limits = { max_params: 40, max_list_items: 50, max_text: 500, max_item_text: 200 };

const isWords = (v: unknown): v is string[] => Array.isArray(v) && v.every((i) => typeof i === 'string');

/** Plain problem with one stored value, mirroring `registry._value_problem`; null when fine or empty. */
function valueProblem(spec: GatewayParamSpec, value: unknown, limits: Limits): string | null {
  if (value === null || value === undefined || value === '') return null;
  const label = spec.label;
  const choices = spec.options.map((o) => o.value);
  switch (spec.type) {
    case 'boolean':
      return typeof value === 'boolean' ? null : `"${label}" must be on or off.`;
    case 'number':
      return typeof value === 'number' && Number.isFinite(value) ? (value < 0 ? `"${label}" cannot be negative.` : null) : `"${label}" must be a number.`;
    case 'text':
    case 'textarea':
      return typeof value !== 'string' ? `"${label}" must be text.` : value.length > limits.max_text ? `"${label}" is too long (at most ${limits.max_text} characters).` : null;
    case 'select':
      return typeof value === 'string' && choices.includes(value) ? null : `Choose one of the listed values for "${label}".`;
    case 'multiselect':
    case 'tags':
    case 'people': {
      if (!isWords(value)) return `"${label}" must be a list of words.`;
      if (value.length > limits.max_list_items) return `"${label}" has too many entries (at most ${limits.max_list_items}).`;
      if (value.some((w) => w.length > limits.max_item_text)) return `An entry of "${label}" is too long (at most ${limits.max_item_text} characters).`;
      if (spec.type === 'multiselect' && value.some((w) => !choices.includes(w))) return `Choose only listed values for "${label}".`;
      return null;
    }
    default:
      return null;
  }
}

/** Problems with the filters of one trigger against its registry spec (unknown or repeated keys, wrong values, caps). */
export function paramIssues(spec: GatewayTriggerSpec, params: readonly GatewayParam[] | undefined, limits: Limits = DEFAULT_LIMITS): GatewayIssue[] {
  const out: GatewayIssue[] = [];
  const list = params ?? [];
  if (list.length > limits.max_params) out.push({ field: 'params', message: `This trigger has too many options (at most ${limits.max_params}).` });
  const byKey = new Map(spec.params.map((p) => [p.key, p]));
  const seen = new Set<string>();
  for (const item of list) {
    const def = byKey.get(item.key);
    if (!def) {
      out.push({ field: `params.${item.key}`, message: 'One of the options is not available for this trigger. Remove it.' });
      continue;
    }
    if (seen.has(item.key) && !def.multiple) out.push({ field: `params.${item.key}`, message: `"${def.label}" is set more than once.` });
    seen.add(item.key);
    const problem = valueProblem(def, item.value, limits);
    if (problem) out.push({ field: `params.${item.key}`, message: problem });
  }
  for (const def of spec.params) {
    if (def.required && !seen.has(def.key)) out.push({ field: `params.${def.key}`, message: `Fill in "${def.label}".` });
  }
  return out;
}

export interface GatewayConfigLike {
  gateway?: string;
  params?: readonly GatewayParam[];
}

/**
 * Everything that stops a chat trigger from going live, as plain sentences. A draft saves regardless; these show as
 * "things to finish" and block publishing. `registry` is null until it has loaded: then only the channel is checked.
 */
export function gatewayTriggerIssues(kind: GatewayKindId, config: GatewayConfigLike, registry: GatewayRegistry | null): GatewayIssue[] {
  const out: GatewayIssue[] = [];
  const name = (config.gateway ?? '').trim();
  if (!name) {
    out.push({ field: 'gateway', message: `${pickPrompt(kind)}.` });
  } else if (registry) {
    const wanted = GATEWAY_TRIGGER_KINDS.find((k) => k.id === kind)?.provider;
    const choice: GatewayChoice | undefined = registry.gateways.find((g) => g.name === name);
    if (!choice) out.push({ field: 'gateway', message: `This ${channelNoun(kind)} is not available to you. ${pickPrompt(kind)} from the list.` });
    else if (wanted && choice.provider !== wanted) out.push({ field: 'gateway', message: `That is not a ${channelNoun(kind)}. ${pickPrompt(kind)}.` });
    else if (!gatewaysForKind(kind, registry.gateways).some((g) => g.name === name)) out.push({ field: 'gateway', message: `${pickPrompt(kind)}.` });
  }
  const nodeType = GATEWAY_TRIGGER_KINDS.find((k) => k.id === kind)!.nodeType;
  const spec = registry?.specs[nodeType];
  if (spec) out.push(...paramIssues(spec, config.params, registry.limits));
  return out;
}
