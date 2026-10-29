import { fieldSelector } from './frameIssues';

const FOCUSABLE = 'input, textarea, select, button, [role="combobox"], [tabindex]:not([tabindex="-1"])';

/** The control for a field inside the panel body, or the message anchor next to it when the control has no test id. */
export function findFieldElement(root: ParentNode, kind: string, field: string): HTMLElement | null {
  const direct = root.querySelector<HTMLElement>(fieldSelector(kind, field));
  if (direct) return direct;
  // Paths between steps and the trigger choice have their own places.
  if (field.startsWith('branch.')) return root.querySelector<HTMLElement>('[data-testid="flow-branches"]');
  if (field === 'type') return root.querySelector<HTMLElement>('[data-testid="flow-trigger-change"]');
  if (field === 'connection') return null;
  const anchor = root.querySelector<HTMLElement>(`[data-testid="flow-error-${kind}-${field}"]`);
  return anchor?.previousElementSibling instanceof HTMLElement ? anchor.previousElementSibling : anchor;
}

/** Scroll a field into view (below the sticky header) and put the cursor in it. Returns false when it is not on screen yet. */
export function focusFieldIn(root: ParentNode, kind: string, field: string): boolean {
  const el = findFieldElement(root, kind, field);
  if (!el) {
    // It may sit in a folded "More options": open those and look again next frame.
    root.querySelectorAll<HTMLElement>('[data-more-options][data-state="closed"] > [role="button"]').forEach((b) => b.click());
    return false;
  }
  el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  const control = el.matches(FOCUSABLE) ? el : el.querySelector<HTMLElement>(FOCUSABLE);
  (control ?? el).focus({ preventScroll: true });
  return true;
}
