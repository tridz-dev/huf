/**
 * Which capability opens which Huf page. One table for the route guards and the navigation, so a person is never shown a
 * link to a page that answers with "You don't have access" (and no page asks the server for data its role may not read).
 *
 * A list means any one of them is enough. PAGE_ACCESS_ANY means "has some Huf role": every other capability would also do.
 */
export const PAGE_ACCESS_ANY = '*';

export type PageCapability = string | readonly string[];

export const PAGE_ACCESS = {
  /** The Hub and the dashboard's chat box need an agent to talk to. */
  hub: ['agent.use', 'chat.use', 'flows.use'],
  agents: 'agent.use',
  executions: 'agent.use',
  /** Dashboard figures come from analytics, which the server only gives to people who see all agents. */
  dashboard: 'agent.view_all',
  /** Agent settings (code in flows, skill sources) are for people who edit things; others have nothing to read there. */
  settings: ['system.settings.manage', 'agent.edit', 'flows.manage'],
  flows: 'flows.use',
} as const satisfies Record<string, PageCapability>;

/** True when the user's capabilities satisfy `required` (a name, a list of alternatives, or PAGE_ACCESS_ANY). */
export function hasPageAccess(capabilities: readonly string[], required: PageCapability | undefined): boolean {
  if (required === undefined) return true;
  if (required === PAGE_ACCESS_ANY) return capabilities.length > 0;
  const wanted = typeof required === 'string' ? [required] : required;
  return wanted.some((c) => c === PAGE_ACCESS_ANY ? capabilities.length > 0 : capabilities.includes(c));
}
