/**
 * Sidebar scope: either the global (unfiltered) chat rail, or scoped to a
 * single HUF Project. Derived from the route (see ChatRail.tsx) - never
 * tracked as separate client state that could drift from the URL.
 */
export type ChatRailScope =
  | { kind: 'global' }
  | { kind: 'project'; projectId: string; projectName: string };
