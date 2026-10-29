/**
 * Doc events a Flow trigger can use: the Flow graph IR enum (graph_ir.schema.json
 * TriggerDocEventNode.config.event). The trigger lives in the node config and is bound when the flow is published.
 */
export const DOC_EVENTS = ['after_insert', 'on_update', 'on_submit', 'on_cancel', 'on_trash'] as const;
export type FlowDocEvent = (typeof DOC_EVENTS)[number];

/** The event as a person says it: "When a customer is ___". */
export const EVENT_WORD: Record<FlowDocEvent, string> = {
  after_insert: 'created',
  on_update: 'changed',
  on_submit: 'submitted',
  on_cancel: 'cancelled',
  on_trash: 'deleted',
};

/**
 * Rank a search: names that start with the text first, then names that contain it, then the same for the module. Letters
 * scattered through a name never match, so searching "todo" finds the To-do and nothing unrelated.
 */
export function filterDoctypes<T extends { name: string; label: string; module: string }>(options: T[], query: string): T[] {
  const q = query.trim().toLowerCase();
  if (!q) return options;
  const score = (d: T) => {
    const names = [d.label.toLowerCase(), d.name.toLowerCase(), d.name.toLowerCase().replace(/\s+/g, '')];
    if (names.some((n) => n.startsWith(q))) return 0;
    if (names.some((n) => n.split(/[\s\-_]+/).some((w) => w.startsWith(q)))) return 1;
    if (names.some((n) => n.includes(q))) return 2;
    return d.module.toLowerCase().includes(q) ? 3 : 4;
  };
  return options
    .map((d) => [score(d), d] as const)
    .filter(([s]) => s < 4)
    .sort((a, b) => a[0] - b[0])
    .map(([, d]) => d);
}
