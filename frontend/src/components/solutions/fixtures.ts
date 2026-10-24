import type { EntryPoint, SolutionOverview } from '@/types/solutions';

export function makeOverview(over: Partial<SolutionOverview> = {}): SolutionOverview {
  return {
    name: 'orders', title: 'Orders', purpose: 'orders', status: 'Live', test_mode: false,
    runs_on: [{ gateway: 'gw1', label: 'Main', phone: '+1 555 0100' }],
    shared: false, entry_count: 2, primary: { type: 'Agent', name: 'order-agent', label: 'Order agent' }, chats_7d: 12,
    description: 'Takes orders.',
    health: { state: 'ok', gateway: 'gw1', quality: null, blame: null },
    reach: { contacts_7d: 30, new_7d: 5 },
    activity: [{ ts: '2026-10-24T10:00:00Z', kind: 'chat', text: 'New order chat' }],
    cost: { sends_24h: 40, cap_share: 0.4, ceiling: 100 },
    limits: { per_day: null, scope: 'Any number' },
    ...over,
  };
}

export function makeEntry(over: Partial<EntryPoint> = {}): EntryPoint {
  return {
    name: 'ep1', gateway: 'gw1', priority: 1, match_type: 'Keyword', match_values: ['refund'], target_type: 'Agent',
    agent: 'order-agent', flow: null, cap_per_day: 30, scope_override: null, allow_first_message: false,
    ceiling: 100, ceiling_source: 'meta_tier', ...over,
  };
}
