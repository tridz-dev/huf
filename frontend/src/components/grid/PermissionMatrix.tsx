/**
 * PermissionMatrix (DESIGN.md §6.11.8): subjects (rows) × capabilities
 * (columns) of checkboxes. Capabilities can imply others ("Edit" implies
 * "Read"): turning one on turns on what it implies, turning one off turns
 * off what depends on it, so the matrix never holds an impossible grant.
 * Arrow keys move between checkboxes (roving tabindex); Space toggles.
 */
import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';

export interface MatrixSubject {
  id: string;
  label: string;
  meta?: ReactNode;
}

export interface MatrixCapability {
  key: string;
  label: string;
  description?: string;
  /** Keys this capability needs, e.g. edit → ['read']. */
  implies?: string[];
}

export type MatrixValue = Record<string, Record<string, boolean>>;

export interface PermissionMatrixProps {
  subjects: MatrixSubject[];
  capabilities: MatrixCapability[];
  value: MatrixValue;
  onChange: (next: MatrixValue, change: { subject: string; capability: string; on: boolean }) => void;
  isDisabled?: (subject: string, capability: string) => boolean;
  /** Header of the subject column, e.g. "Agent". */
  subjectLabel?: string;
  label: string;
  /** Trailing cell per row (e.g. a remove action). */
  rowEnd?: (subject: MatrixSubject) => ReactNode;
  className?: string;
}

/** Apply one toggle with implication closure. Pure; exported for tests and server previews. */
export function applyGrant(caps: MatrixCapability[], row: Record<string, boolean>, key: string, on: boolean): Record<string, boolean> {
  const next = { ...row, [key]: on };
  const byKey = new Map(caps.map((c) => [c.key, c]));
  if (on) {
    const stack = [...(byKey.get(key)?.implies ?? [])];
    while (stack.length) {
      const k = stack.pop()!;
      if (!next[k]) { next[k] = true; stack.push(...(byKey.get(k)?.implies ?? [])); }
    }
  } else {
    let changed = true;
    while (changed) {
      changed = false;
      for (const c of caps) if (next[c.key] && c.implies?.some((k) => !next[k])) { next[c.key] = false; changed = true; }
    }
  }
  return next;
}

export function PermissionMatrix({ subjects, capabilities, value, onChange, isDisabled, subjectLabel = 'Who', label, rowEnd, className }: PermissionMatrixProps) {
  const [pos, setPos] = useState({ r: 0, c: 0 });
  const table = useRef<HTMLTableElement>(null);

  const toggle = (s: string, k: string, on: boolean) => {
    const row = applyGrant(capabilities, value[s] ?? {}, k, on);
    onChange({ ...value, [s]: row }, { subject: s, capability: k, on });
  };

  const onKey = (e: KeyboardEvent) => {
    const d = ({ ArrowDown: [1, 0], ArrowUp: [-1, 0], ArrowRight: [0, 1], ArrowLeft: [0, -1] } as Record<string, [number, number]>)[e.key];
    if (!d) return;
    e.preventDefault();
    const next = { r: Math.max(0, Math.min(subjects.length - 1, pos.r + d[0])), c: Math.max(0, Math.min(capabilities.length - 1, pos.c + d[1])) };
    setPos(next);
    table.current?.querySelector<HTMLElement>(`[data-pos="${next.r}:${next.c}"]`)?.focus();
  };

  return (
    <div className={cn('overflow-x-auto rounded-lg border border-line bg-panel', className)}>
      <table ref={table} aria-label={label} onKeyDown={onKey} className="w-full border-separate border-spacing-0 text-ui-text">
        <thead>
          <tr className="bg-paper-deep">
            <th scope="col" className="border-b border-line px-4 py-2 text-left text-micro font-medium text-steel">{subjectLabel}</th>
            {capabilities.map((c) => (
              <th key={c.key} scope="col" title={c.description} className="w-24 border-b border-line px-2 py-2 text-center text-micro font-medium text-steel">
                {c.label}
              </th>
            ))}
            {rowEnd && <th className="w-12 border-b border-line"><span className="sr-only">Actions</span></th>}
          </tr>
        </thead>
        <tbody>
          {subjects.map((s, r) => (
            <tr key={s.id} className="hover:bg-paper-deep/60">
              <th scope="row" className="border-b border-line px-4 py-2.5 text-left font-medium text-ink">
                {s.label}
                {s.meta && <span className="block text-micro font-normal text-steel">{s.meta}</span>}
              </th>
              {capabilities.map((c, ci) => (
                <td key={c.key} className="border-b border-line text-center">
                  <Checkbox data-pos={`${r}:${ci}`} tabIndex={pos.r === r && pos.c === ci ? 0 : -1}
                    aria-label={`${c.label} for ${s.label}`} checked={Boolean(value[s.id]?.[c.key])} disabled={isDisabled?.(s.id, c.key)}
                    onFocus={() => setPos({ r, c: ci })} onCheckedChange={(v) => toggle(s.id, c.key, v === true)} />
                </td>
              ))}
              {rowEnd && <td className="border-b border-line px-2 text-right">{rowEnd(s)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
