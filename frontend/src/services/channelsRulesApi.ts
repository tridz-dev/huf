import { call } from '@/lib/frappe-sdk';

const BASE = 'huf.ai.channels.rules_api';

export type RuleType = 'keyword' | 'first_message' | 'contact_attribute' | 'fallback';
export type RuleTargetType = 'solution' | 'agent' | 'human';

export interface RoutingRule {
  rule_type: RuleType;
  match_value: string;
  attribute: string;
  target_type: RuleTargetType;
  target: string;
  priority: number;
  enabled: 0 | 1;
}

const unwrap = <T>(res: unknown): T =>
  (res && typeof res === 'object' && 'message' in res ? (res as { message: T }).message : res) as T;

export async function getRules(gateway: string): Promise<RoutingRule[]> {
  return unwrap<RoutingRule[]>(await call.get(`${BASE}.get_rules`, { gateway })) ?? [];
}

export async function saveRules(gateway: string, rules: RoutingRule[]): Promise<RoutingRule[]> {
  return unwrap<RoutingRule[]>(await call.post(`${BASE}.save_rules`, { gateway, rules: JSON.stringify(rules) })) ?? [];
}

/** Which ecosystem apps are installed; endpoint may not exist yet, in which case everything is treated as available. */
export interface EcosystemApps { helpdesk: boolean; crm: boolean }

export async function getEcosystemApps(): Promise<EcosystemApps> {
  const all = { helpdesk: true, crm: true };
  try {
    const r = unwrap<unknown>(await call.get('huf.ai.channels.ecosystem.get_ecosystem', {}));
    if (!r || typeof r !== 'object') return all;
    const o = r as Record<string, unknown>;
    const list = Array.isArray(r) ? (r as unknown[]) : Array.isArray(o.apps) ? (o.apps as unknown[]) : null;
    const flag = (k: string, v: unknown): boolean =>
      typeof v === 'boolean' ? v : v && typeof v === 'object' ? flag(k, (v as Record<string, unknown>).installed ?? (v as Record<string, unknown>).available ?? true) : v == null ? true : !!v;
    if (list) {
      const names = list.map((x) => String(typeof x === 'object' && x ? (x as { name?: string }).name ?? '' : x).toLowerCase());
      return { helpdesk: names.includes('helpdesk'), crm: names.includes('crm') };
    }
    return { helpdesk: flag('helpdesk', o.helpdesk), crm: flag('crm', o.crm) };
  } catch {
    return all;
  }
}

const WIDGETS = 'huf.ai.channels.widgets';

export interface ClickToChat { wa_me_url: string; qr_svg: string | null }

export async function getClickToChat(gateway: string, prefill: string, ref: string, phone?: string | null): Promise<ClickToChat> {
  return unwrap<ClickToChat>(await call.get(`${WIDGETS}.get_click_to_chat`, { gateway, prefill, ref, phone: phone ?? undefined }));
}

export async function getWidgetSnippet(gateway: string, prefill: string, ref: string, label: string, position: string, phone?: string | null): Promise<string> {
  const res = unwrap<{ snippet: string }>(await call.get(`${WIDGETS}.get_widget_snippet`, { gateway, prefill, ref, label, position, phone: phone ?? undefined }));
  return res.snippet;
}
