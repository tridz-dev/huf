import type { GatewayChoice, GatewayParam, GatewayParamValue } from './gatewayTrigger.types';
import { channelWord, gatewayDisplayName, pickPrompt, type GatewayKindId } from './gatewayWords';
import { isEmptyParam } from './gatewayParams';

interface Cfg {
  gateway?: string;
  params?: readonly GatewayParam[];
}

const words = (v: GatewayParamValue | undefined): string[] => (Array.isArray(v) ? v.filter((w) => w.trim()) : typeof v === 'string' && v.trim() ? [v.trim()] : []);
function quoted(list: string[]): string {
  const q = list.slice(0, 3).map((w) => `"${w.length > 24 ? `${w.slice(0, 23)}…` : w}"`);
  if (q.length === 1) return q[0];
  const last = q.pop();
  return `${q.join(', ')} or ${last}${list.length > 3 ? ' or more' : ''}`;
}
const get = (params: readonly GatewayParam[] | undefined, key: string) => params?.find((p) => p.key === key)?.value;

/** The one filter worth a line on the card, in plain words; null when the trigger takes every message. */
export function filterSummary(config: Cfg, compact = false): string | null {
  const keywords = words(get(config.params, 'keywords'));
  if (keywords.length) return compact ? `Contains ${quoted(keywords)}` : `Only messages that contain ${quoted(keywords)}`;
  const starts = words(get(config.params, 'starts_with'));
  if (starts.length) return compact ? `Starts with ${quoted(starts)}` : `Only messages that start with ${quoted(starts)}`;
  const commands = words(get(config.params, 'commands'));
  if (commands.length) return `Only ${commands.slice(0, 3).map((c) => `/${c.replace(/^\//, '')}`).join(', ')}${commands.length > 3 ? ' and more' : ''}`;
  const buttons = words(get(config.params, 'button_reply_ids')).concat(words(get(config.params, 'button_payloads')));
  if (buttons.length) return 'Only when they press a chosen button';
  const kinds = words(get(config.params, 'message_kinds'));
  if (kinds.length) return `Only ${kinds.slice(0, 2).join(' and ')} messages${kinds.length > 2 ? ' and more' : ''}`;
  const senders = words(get(config.params, 'only_senders'));
  if (senders.length) return `Only messages from ${senders.length === 1 ? (senders[0].length > 24 ? `${senders[0].slice(0, 23)}…` : senders[0]) : `${senders.length} people`}`;
  const others = (config.params ?? []).filter((p) => !isEmptyParam(p.value) && !['max_runs_per_sender_per_hour', 'allow_parallel', 'ignore_bots'].includes(p.key));
  return others.length ? 'Only some messages' : null;
}

/** "When someone messages Support (WhatsApp)" on the card; with a filter, the filter instead; unset: "Pick a WhatsApp number". */
export function gatewaySubtitle(kind: GatewayKindId, config: Cfg, gateways?: readonly GatewayChoice[] | null, compact = false): string {
  if (!config.gateway?.trim()) return pickPrompt(kind);
  const filter = filterSummary(config, compact);
  // On the narrow card the filter must fit two lines: shorter filter words and no "(never sends)" style note after the channel name.
  if (filter) return `${compact ? gatewayDisplayName(config.gateway, gateways).replace(/\s*\([^)]*\)\s*$/, '') : gatewayDisplayName(config.gateway, gateways)} · ${filter}`;
  const word = channelWord(kind, config.gateway, gateways);
  const name = gatewayDisplayName(config.gateway, gateways);
  // On the card the channel word and a "(never sends)" style note are left out: they only push the name off the two lines.
  const plain = name.replace(/\s*\([^)]*\)\s*$/, '');
  if (compact && plain !== name) return `When someone messages ${plain}`;
  return `When someone messages ${name}${word ? ` (${word})` : ''}`;
}

/** "someone messages Support on WhatsApp" for lists and the publish dialog. */
export function gatewayPhrase(kind: GatewayKindId, config: Cfg, gateways?: readonly GatewayChoice[] | null): string {
  const name = gatewayDisplayName(config.gateway, gateways);
  const word = channelWord(kind, config.gateway, gateways);
  if (!name) return word ? `someone messages you on ${word}` : 'someone sends a chat message';
  return `someone messages ${name}${word ? ` on ${word}` : ''}`;
}

/** The unpublish line: "Messages to Support will no longer start it". */
export function gatewayStopLine(config: Cfg, gateways?: readonly GatewayChoice[] | null): string {
  const name = gatewayDisplayName(config.gateway, gateways);
  return name ? `Messages to ${name} will no longer start it.` : 'Chat messages will no longer start it.';
}
