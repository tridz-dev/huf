/**
 * StepCard and OneCardCreate (DESIGN.md §6.12.8).
 * OneCardCreate: the whole "new thing" flow on one centred card — only the
 * fields needed to get something working, a primary verb that creates and
 * opens it ("Create and try it"), ⌘Enter submits. Everything else is set later.
 * StepCard: a numbered card for a short guided sequence on one page.
 */
import type { FormEvent, KeyboardEvent, ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';

export interface StepCardProps {
  step?: number;
  title: ReactNode;
  description?: ReactNode;
  state?: 'current' | 'done' | 'upcoming';
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
}

export function StepCard({ step, title, description, state = 'current', children, footer, className }: StepCardProps) {
  return (
    <section aria-current={state === 'current' ? 'step' : undefined} data-state={state}
      className={cn('rounded-lg border bg-panel p-5', state === 'current' ? 'border-line shadow-md' : 'border-line opacity-80', className)}>
      <div className="flex items-start gap-3">
        {step !== undefined && (
          <span aria-hidden="true" className={cn('flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-meta',
            state === 'done' ? 'bg-good-tint text-good' : state === 'current' ? 'bg-ink text-primary-foreground' : 'bg-paper-deep text-steel')}>
            {state === 'done' ? '✓' : step}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <h2 className="text-ui-text font-semibold text-ink">{step !== undefined && <span className="sr-only">Step {step}: </span>}{title}</h2>
          {description && <p className="mt-0.5 text-micro text-steel">{description}</p>}
        </div>
      </div>
      {children && <div className="mt-4 space-y-4">{children}</div>}
      {footer && <div className="mt-4 flex justify-end gap-2">{footer}</div>}
    </section>
  );
}

export interface OneCardCreateProps {
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  submitLabel: string;
  onSubmit: () => void;
  busy?: boolean;
  disabled?: boolean;
  /** Secondary link-weight action, e.g. "Start from scratch". */
  secondary?: ReactNode;
  className?: string;
}

export function OneCardCreate({ title, description, children, submitLabel, onSubmit, busy, disabled, secondary, className }: OneCardCreateProps) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!busy && !disabled) onSubmit();
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) submit(e);
  };
  return (
    <form noValidate onSubmit={submit} onKeyDown={onKey} aria-busy={busy || undefined}
      className={cn('mx-auto w-full max-w-xl rounded-lg border border-line bg-panel p-6 shadow-md', className)}>
      <h1 className="text-title font-semibold text-ink">{title}</h1>
      {description && <p className="mt-1 text-ui-text text-steel">{description}</p>}
      <div className="mt-5 space-y-4">{children}</div>
      <div className="mt-6 flex items-center justify-end gap-3">
        {secondary}
        <Button type="submit" disabled={disabled || busy} aria-keyshortcuts="Meta+Enter">
          {busy && <Spinner role="presentation" aria-hidden="true" className="h-3.5 w-3.5" />}
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
