/**
 * PresetSelector (DESIGN.md §6.12.4): named presets instead of raw sliders
 * ("Precise · Balanced · Creative"), with an optional "Custom" that reveals
 * the raw controls. A radio group: arrow keys move and select.
 */
import { useRef, type KeyboardEvent, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export const CUSTOM_PRESET = '__custom__';

export interface Preset<V extends string = string> {
  value: V;
  label: string;
  description?: string;
  recommended?: boolean;
}

export interface PresetSelectorProps<V extends string = string> {
  presets: Preset<V>[];
  value: V | typeof CUSTOM_PRESET;
  onChange: (value: V | typeof CUSTOM_PRESET) => void;
  label: string;
  /** Raw controls shown when "Custom" is chosen. Omit to hide the Custom option. */
  custom?: ReactNode;
  customLabel?: string;
  className?: string;
}

export function PresetSelector<V extends string = string>({ presets, value, onChange, label, custom, customLabel = 'Custom', className }: PresetSelectorProps<V>) {
  const options: Preset<V | typeof CUSTOM_PRESET>[] = custom ? [...presets, { value: CUSTOM_PRESET, label: customLabel, description: 'Set it yourself' }] : presets;
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const onKey = (e: KeyboardEvent, i: number) => {
    const d = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const n = (i + d + options.length) % options.length;
    onChange(options[n].value);
    refs.current[n]?.focus();
  };
  const current = options.some((o) => o.value === value) ? value : options[0]?.value;
  return (
    <div className={cn('space-y-3', className)}>
      <div role="radiogroup" aria-label={label} className="grid gap-2 sm:grid-cols-[repeat(auto-fit,minmax(9rem,1fr))]">
        {options.map((o, i) => {
          const on = o.value === current;
          return (
            <button key={o.value} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={on} tabIndex={on ? 0 : -1}
              onClick={() => onChange(o.value)} onKeyDown={(e) => onKey(e, i)}
              className={cn('rounded-lg border px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                on ? 'border-signal bg-signal/5' : 'border-line bg-panel hover:bg-paper-deep')}>
              <span className="flex items-center gap-1.5 text-ui-text font-medium text-ink">
                {o.label}
                {o.recommended && <span className="text-meta font-normal text-signal-ink">Recommended</span>}
              </span>
              {o.description && <span className="mt-0.5 block text-micro text-steel">{o.description}</span>}
            </button>
          );
        })}
      </div>
      {custom && current === CUSTOM_PRESET && <div className="space-y-4 rounded-lg border border-line p-4">{custom}</div>}
    </div>
  );
}
