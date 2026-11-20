/**
 * FormSection and inline-validation helpers (DESIGN.md §6.12.2).
 * A section is a titled panel of fields. Fields use `ui/field` (`required`,
 * `error`), which already wires the label, the required star, aria-invalid
 * and the error note. These helpers cover what Field does not:
 *   RequiredMark   the star for a custom label (with an sr-only "required")
 *   FieldError     an error line for a control not wrapped in Field
 *   focusFirstError  move focus to the first invalid control after a save
 *   ErrorSummary   one banner listing every error as a jump link
 */
import { useId, type ReactNode } from 'react';
import { AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface FormSectionProps {
  title: ReactNode;
  description?: ReactNode;
  /** Right side of the section head, e.g. a "Change" button. */
  actions?: ReactNode;
  children: ReactNode;
  id?: string;
  className?: string;
}

export function FormSection({ title, description, actions, children, id, className }: FormSectionProps) {
  const auto = useId();
  const headId = `${id ?? auto}-title`;
  return (
    <section id={id} aria-labelledby={headId} className={cn('rounded-lg border border-line bg-panel p-5', className)}>
      <div className="mb-4 flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h2 id={headId} className="text-subtitle font-semibold text-ink">{title}</h2>
          {description && <p className="mt-0.5 text-ui-text text-steel">{description}</p>}
        </div>
        {actions}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

export function RequiredMark() {
  return (
    <>
      <span aria-hidden="true" className="ml-0.5 text-destructive">*</span>
      <span className="sr-only"> (required)</span>
    </>
  );
}

export function FieldError({ id, children }: { id?: string; children?: ReactNode }) {
  if (!children) return null;
  return <p id={id} role="alert" className="mt-1 text-micro text-destructive">{children}</p>;
}

/** Focus and reveal the first `[aria-invalid="true"]` inside `root`. Returns whether one was found. */
export function focusFirstError(root: ParentNode | null = typeof document === 'undefined' ? null : document): boolean {
  const el = root?.querySelector<HTMLElement>('[aria-invalid="true"]');
  if (!el) return false;
  // The flagged element may be a wrapper around the real control: focus the control so the caret and focus ring land on it.
  const native = /^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(el.tagName) ? el : el.querySelector<HTMLElement>('textarea, input:not([type="hidden"]), select, button, [contenteditable="true"]');
  const target = native ?? el;
  target.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
  target.focus();
  return true;
}

export interface FormError {
  /** Id of the control to focus. */
  fieldId: string;
  message: string;
}

/** One banner for a failed save: "2 things need fixing" + a jump link per error. Not rendered when empty. */
export function ErrorSummary({ errors, onSelect, className }: { errors: FormError[]; onSelect?: (fieldId: string) => void; className?: string }) {
  if (errors.length === 0) return null;
  const go = (id: string) => {
    if (onSelect) return onSelect(id);
    const el = document.getElementById(id);
    el?.scrollIntoView?.({ block: 'center' });
    el?.focus();
  };
  return (
    <div role="alert" data-testid="error-summary" className={cn('rounded-lg border border-destructive/30 bg-destructive-tint px-4 py-3', className)}>
      <p className="flex items-center gap-2 text-ui-text font-medium text-destructive">
        <AlertCircle aria-hidden="true" className="h-4 w-4 shrink-0" />
        {errors.length === 1 ? '1 thing needs fixing' : `${errors.length} things need fixing`}
      </p>
      <ul className="mt-1 space-y-0.5 pl-6 text-micro">
        {errors.map((e) => (
          <li key={e.fieldId}>
            <a href={`#${e.fieldId}`} className="text-ink underline underline-offset-2 hover:text-destructive"
              onClick={(ev) => { ev.preventDefault(); go(e.fieldId); }}>
              {e.message}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
