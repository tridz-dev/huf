/**
 * Field, FieldRow, FieldAction: the RHF-free form field primitive.
 *
 * USAGE RULE: every control in a row is a Field or a FieldAction. No bare
 * controls in a FieldRow. A Field is label slot (fixed height), control,
 * then a note row (hint / error / counter). The label slot and note row
 * use the --field-label-h / --field-gap / --field-note-h tokens, which
 * ui/form.tsx (FormItem/FormLabel/FormDescription/FormMessage) shares, so
 * RHF and non-RHF forms are identical.
 *
 * - Unlabelled control next to labelled ones (button, switch, select):
 *   wrap it in <FieldAction> (or <Field reserveLabel>) so it aligns.
 * - Helper text of differing length/presence across a row: set
 *   `reserveNote` on the fields so the control tops/bottoms stay aligned.
 */
import * as React from 'react';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

/** Shared class tokens (also consumed by ui/form.tsx). */
export const FIELD_LABEL_SLOT =
  'flex h-[var(--field-label-h)] items-center mb-[var(--field-gap)]';
export const FIELD_NOTE =
  'min-h-[var(--field-note-h)] mt-[var(--field-gap)] text-micro leading-4';

export interface FieldControlProps {
  id: string;
  'aria-describedby'?: string;
  'aria-invalid'?: boolean;
}

export interface FieldProps {
  label?: React.ReactNode;
  hint?: React.ReactNode;
  error?: React.ReactNode;
  /** e.g. 12/60; turns red past the limit. */
  counter?: { length: number; max: number };
  /** Right-aligned content in the label slot. */
  labelExtra?: React.ReactNode;
  required?: boolean;
  id?: string;
  size?: 'sm' | 'md';
  /** Empty aria-hidden label slot so an unlabelled control aligns. */
  reserveLabel?: boolean;
  /** Always render the note row (reserved height). */
  reserveNote?: boolean;
  className?: string;
  children: React.ReactNode | ((props: FieldControlProps) => React.ReactNode);
}

export function Field({
  label,
  hint,
  error,
  counter,
  labelExtra,
  required,
  id,
  size = 'md',
  reserveLabel,
  reserveNote,
  className,
  children,
}: FieldProps) {
  const autoId = React.useId();
  const fieldId = id ?? autoId;
  const noteId = `${fieldId}-note`;
  const hasNoteText = Boolean(error || hint);
  const showNote = hasNoteText || Boolean(counter) || Boolean(reserveNote);

  const controlProps: FieldControlProps = { id: fieldId };
  if (hasNoteText) controlProps['aria-describedby'] = noteId;
  if (error) controlProps['aria-invalid'] = true;

  let control: React.ReactNode;
  if (typeof children === 'function') {
    control = children(controlProps);
  } else if (React.isValidElement<Record<string, unknown>>(children) && typeof children.type !== 'symbol') {
    const p = children.props;
    const inject: Record<string, unknown> = {};
    // Only auto-wire the id when the caller did not supply one; with an
    // explicit id the caller owns which element carries it.
    if (id === undefined && p.id === undefined) inject.id = controlProps.id;
    if (p['aria-describedby'] === undefined && controlProps['aria-describedby']) {
      inject['aria-describedby'] = controlProps['aria-describedby'];
    }
    if (p['aria-invalid'] === undefined && controlProps['aria-invalid']) inject['aria-invalid'] = true;
    control = Object.keys(inject).length ? React.cloneElement(children, inject) : children;
  } else {
    control = children;
  }

  const hasLabel = label !== undefined && label !== null && label !== false;

  return (
    <div className={cn('flex min-w-0 flex-col', className)}>
      {hasLabel ? (
        <div data-field-label className={cn(FIELD_LABEL_SLOT, 'justify-between gap-2')}>
          <Label htmlFor={fieldId} size={size === 'sm' ? 'sm' : 'default'}>
            {label}
            {required && <span aria-hidden="true" className="ml-0.5 text-destructive">*</span>}
          </Label>
          {labelExtra}
        </div>
      ) : reserveLabel ? (
        <div data-field-label aria-hidden="true" className={cn(FIELD_LABEL_SLOT, 'justify-between gap-2')} />
      ) : null}
      {control}
      {showNote && (
        <div data-field-note className={cn(FIELD_NOTE, 'flex justify-between gap-3')}>
          {hasNoteText && (
            <p
              id={noteId}
              role={error ? 'alert' : undefined}
              className={error ? 'text-destructive' : 'text-steel'}
            >
              {error || hint}
            </p>
          )}
          {counter && (
            <span className={cn('ml-auto shrink-0', counter.length > counter.max ? 'text-destructive' : 'text-steel')}>
              {counter.length}/{counter.max}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

const COLS: Record<number, string> = {
  1: 'grid-cols-1',
  2: 'grid-cols-2',
  3: 'grid-cols-3',
  4: 'grid-cols-4',
  5: 'grid-cols-5',
  6: 'grid-cols-6',
};

export interface FieldRowProps extends React.HTMLAttributes<HTMLDivElement> {
  /**
   * Equal columns (1-6). Default: one column per child. For custom
   * templates (e.g. "1fr auto") pass a static grid-cols-[...] class via
   * className; it overrides this.
   */
  cols?: 1 | 2 | 3 | 4 | 5 | 6;
}

/** Grid with items-end, gap-3 and min-w-0 children (see header rule). */
export function FieldRow({ cols, className, children, ...props }: FieldRowProps) {
  const n = cols ?? Math.min(Math.max(React.Children.count(children), 1), 6);
  return (
    <div
      {...props}
      data-field-row=""
      className={cn('grid items-end gap-3 [&>*]:min-w-0', COLS[n], className)}
    >
      {children}
    </div>
  );
}

/** A button/switch in a FieldRow: a Field with a reserved (empty) label slot. */
export function FieldAction({
  children,
  className,
  reserveNote,
}: {
  children: React.ReactNode;
  className?: string;
  reserveNote?: boolean;
}) {
  return (
    <Field reserveLabel reserveNote={reserveNote} className={className}>
      {children}
    </Field>
  );
}
