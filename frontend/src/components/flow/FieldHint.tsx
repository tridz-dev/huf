import type { ReactNode } from 'react';

/** One short line under a field: what it is for, or an example. Plain text, always wraps (never cut off). */
export function FieldHint({ children, testId, className }: { children: ReactNode; testId?: string; className?: string }) {
  return (
    <p className={`mt-1 text-micro leading-snug text-muted-foreground break-words ${className ?? ''}`} data-testid={testId}>
      {children}
    </p>
  );
}

/** A folded "examples" block: keeps the form short, but the examples are one click away. */
export function Examples({ title = 'Examples', testId, children }: { title?: string; testId?: string; children: ReactNode }) {
  return (
    <details className="mt-1 text-micro text-muted-foreground" data-testid={testId}>
      <summary className="cursor-pointer select-none">{title}</summary>
      <div className="mt-1 space-y-1 break-words">{children}</div>
    </details>
  );
}

export function Code({ children }: { children: ReactNode }) {
  return <code className="rounded bg-muted/60 px-1 py-0.5 font-mono text-micro break-all">{children}</code>;
}
