/**
 * Arrow-key travel between steps (keyboard users and screen readers): Down goes to the step a connection leads to, Up to the
 * step that leads here, Left and Right to the neighbour on the same row. Pure, so the choices are unit tested.
 */

export type ArrowKey = 'ArrowUp' | 'ArrowDown' | 'ArrowLeft' | 'ArrowRight';

interface Step {
  id: string;
  position: { x: number; y: number };
}
interface Link {
  source: string;
  target: string;
}

/** Steps whose top edges are within this many px count as the same row. */
const SAME_ROW = 40;

export const isArrowKey = (key: string): key is ArrowKey => key === 'ArrowUp' || key === 'ArrowDown' || key === 'ArrowLeft' || key === 'ArrowRight';

/**
 * The id of the step to move to from `current`, or null when there is none in that direction. Among several
 * connections the leftmost step comes first (the "Yes" side before the "No" side).
 */
export function nextStepFor(key: ArrowKey, current: string, steps: Step[], links: Link[]): string | null {
  const here = steps.find((s) => s.id === current);
  if (!here) return null;
  const byId = new Map(steps.map((s) => [s.id, s]));
  const leftToRight = (ids: string[]) =>
    [...new Set(ids)].map((id) => byId.get(id)).filter((s): s is Step => !!s && s.id !== current).sort((a, b) => a.position.x - b.position.x || a.position.y - b.position.y);
  if (key === 'ArrowDown') return leftToRight(links.filter((l) => l.source === current).map((l) => l.target))[0]?.id ?? null;
  if (key === 'ArrowUp') return leftToRight(links.filter((l) => l.target === current).map((l) => l.source))[0]?.id ?? null;
  const row = steps.filter((s) => Math.abs(s.position.y - here.position.y) < SAME_ROW).sort((a, b) => a.position.x - b.position.x);
  const at = row.findIndex((s) => s.id === current);
  return (key === 'ArrowRight' ? row[at + 1] : row[at - 1])?.id ?? null;
}
