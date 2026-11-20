/**
 * Small form-binding helpers shared by the Setup / Advanced / Access tabs.
 * They keep the tabs controlled by the page's react-hook-form instance
 * (same AgentFormValues shape as the legacy tabs) while using ui/field for
 * labels, required stars and inline errors.
 */
import type { ReactNode } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ToggleRow } from '@/components/builder';
import type { AgentFormValues } from '../types';

export type AgentForm = UseFormReturn<AgentFormValues>;

export function useFormBinding(form: AgentForm) {
  const errors = form.formState.errors;
  return {
    get: <K extends keyof AgentFormValues>(name: K): AgentFormValues[K] => form.watch(name),
    set: <K extends keyof AgentFormValues>(name: K, value: AgentFormValues[K]) =>
      form.setValue(name, value as never, { shouldDirty: true, shouldTouch: true, shouldValidate: form.formState.isSubmitted }),
    error: (name: keyof AgentFormValues): string | undefined => {
      const e = errors[name] as { message?: unknown } | undefined;
      return typeof e?.message === 'string' ? e.message : undefined;
    },
  };
}

export function parseOptionalNumber(value: string, parser: (v: string) => number): number | undefined {
  if (value === '') return undefined;
  const n = parser(value);
  return Number.isNaN(n) ? undefined : n;
}

export function NumberField({ label, hint, error, value, onChange, placeholder, min, max, step, float, disabled, required }: {
  label: ReactNode; hint?: ReactNode; error?: ReactNode; value: number | undefined; onChange: (v: number | undefined) => void;
  placeholder?: string; min?: number; max?: number; step?: number; float?: boolean; disabled?: boolean; required?: boolean;
}) {
  return (
    <Field label={label} hint={hint} error={error} required={required}>
      <Input type="number" min={min} max={max} step={step} placeholder={placeholder} disabled={disabled}
        value={value?.toString() ?? ''}
        onChange={(e) => onChange(parseOptionalNumber(e.target.value, float ? parseFloat : (v) => parseInt(v, 10)))} />
    </Field>
  );
}

export interface SelectOption { value: string; label: string }

export function SelectField({ label, hint, error, value, onChange, options, placeholder, disabled, required }: {
  label: ReactNode; hint?: ReactNode; error?: ReactNode; value: string | undefined; onChange: (v: string) => void;
  options: SelectOption[]; placeholder?: string; disabled?: boolean; required?: boolean;
}) {
  return (
    <Field label={label} hint={hint} error={error} required={required}>
      {(p) => (
        <Select value={value ?? ''} onValueChange={onChange} disabled={disabled}>
          <SelectTrigger {...p}><SelectValue placeholder={placeholder} /></SelectTrigger>
          <SelectContent>
            {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
          </SelectContent>
        </Select>
      )}
    </Field>
  );
}

/** A plain on/off setting as a ToggleRow bound to a boolean form field. */
export function BoolRow({ form, name, title, description, disabled }: { form: AgentForm; name: keyof AgentFormValues; title: ReactNode; description?: ReactNode; disabled?: boolean }) {
  const checked = Boolean(form.watch(name));
  return (
    <ToggleRow title={title} description={description} checked={checked} disabled={disabled}
      onCheckedChange={(v) => form.setValue(name, v as never, { shouldDirty: true, shouldTouch: true })} />
  );
}
