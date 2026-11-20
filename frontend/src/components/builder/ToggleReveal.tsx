/**
 * ToggleReveal and ToggleRow (DESIGN.md §6.12.3).
 * ToggleReveal: a switch whose "on" reveals the settings that only matter
 * when it is on (a channel, a feature). Off = the settings are not rendered.
 * ToggleRow: a list row for an optional item (an ability, an integration):
 * title, status line with a tone dot, trailing actions, and its switch.
 */
import { useId, type ReactNode } from 'react';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { TONE_TEXT, ToneDot, type Tone } from '@/components/patterns';
import { cn } from '@/lib/utils';

export interface ToggleRevealProps {
  label: ReactNode;
  /** What turning it on does, in one sentence. */
  description?: ReactNode;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  icon?: ReactNode;
  /** Short state on the right when on, e.g. a status sentence. */
  status?: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function ToggleReveal({ label, description, checked, onCheckedChange, disabled, icon, status, children, className }: ToggleRevealProps) {
  const id = useId();
  const regionId = `${id}-settings`;
  return (
    <div data-state={checked ? 'on' : 'off'} className={cn('rounded-lg border border-line bg-panel', className)}>
      <div className="flex items-start gap-3 p-4">
        {icon && <span aria-hidden="true" className="mt-0.5 text-steel">{icon}</span>}
        <div className="min-w-0 flex-1">
          <Label htmlFor={id} className="font-medium text-ink">{label}</Label>
          {description && <p id={`${id}-desc`} className="text-micro text-steel">{description}</p>}
        </div>
        {checked && status && <div className="text-micro text-steel">{status}</div>}
        <Switch id={id} checked={checked} disabled={disabled} onCheckedChange={onCheckedChange}
          aria-describedby={description ? `${id}-desc` : undefined} aria-controls={children ? regionId : undefined} aria-expanded={children ? checked : undefined} />
      </div>
      {children && checked && (
        <div id={regionId} role="region" aria-label={typeof label === 'string' ? `${label} settings` : 'Settings'}
          className="space-y-4 border-t border-line px-4 py-4 motion-safe:animate-drop">
          {children}
        </div>
      )}
    </div>
  );
}

export interface ToggleRowProps {
  title: ReactNode;
  description?: ReactNode;
  status?: ReactNode;
  statusTone?: Tone;
  icon?: ReactNode;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  /** Before the switch, e.g. an OverflowMenu. */
  actions?: ReactNode;
  className?: string;
}

export function ToggleRow({ title, description, status, statusTone = 'neutral', icon, checked, onCheckedChange, disabled, actions, className }: ToggleRowProps) {
  const id = useId();
  return (
    <div data-testid="toggle-row" className={cn('flex items-center gap-3 border-b border-line px-4 py-3 last:border-b-0', className)}>
      {icon && <span aria-hidden="true" className="text-steel">{icon}</span>}
      <div className="min-w-0 flex-1">
        <Label htmlFor={id} className="font-medium text-ink">{title}</Label>
        {description && <p className="text-micro text-steel">{description}</p>}
        {status && (
          <p className={cn('mt-0.5 flex items-center gap-1.5 text-micro', TONE_TEXT[statusTone])}>
            <ToneDot tone={statusTone} />
            {status}
          </p>
        )}
      </div>
      {actions}
      <Switch id={id} checked={checked} disabled={disabled} onCheckedChange={onCheckedChange} />
    </div>
  );
}
