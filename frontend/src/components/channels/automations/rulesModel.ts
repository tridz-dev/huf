import type { RoutingRule } from '@/services/channelsRulesApi';

export const RULE_TYPES = [
  { value: 'keyword', label: 'Keyword' },
  { value: 'first_message', label: 'First message' },
  { value: 'contact_attribute', label: 'Contact attribute' },
  { value: 'fallback', label: 'Fallback' },
] as const;

export const TARGET_TYPES = [
  { value: 'solution', label: 'Solution' },
  { value: 'agent', label: 'Agent' },
  { value: 'human', label: 'Human' },
] as const;

export const newRule = (): RoutingRule => ({
  rule_type: 'keyword', match_value: '', attribute: '', target_type: 'solution', target: '', priority: 0, enabled: 1,
});

export const renumber = (rules: RoutingRule[]): RoutingRule[] => rules.map((r, i) => ({ ...r, priority: i + 1 }));

export function move(rules: RoutingRule[], i: number, dir: -1 | 1): RoutingRule[] {
  const j = i + dir;
  if (j < 0 || j >= rules.length) return rules;
  const next = [...rules];
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}

export function validateRules(rules: RoutingRule[]): string | null {
  for (const [i, r] of rules.entries()) {
    if (r.target_type !== 'human' && !r.target) return `Rule ${i + 1}: choose a target.`;
    if ((r.rule_type === 'keyword' || r.rule_type === 'first_message') && !r.match_value.trim()) return `Rule ${i + 1}: enter what to match.`;
    if (r.rule_type === 'contact_attribute' && !r.attribute.trim()) return `Rule ${i + 1}: enter the attribute.`;
  }
  return null;
}
