import { useEffect, useId, useMemo, useState } from 'react';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { EventAliasSummary } from '@/services/automationApi';
import { useEventAliases } from './useEventAliases';
import { AliasLoadError, AliasStatusNotice, EmptyAliasHint } from './AppEventNotices';

const CUSTOM_VALUE = '__custom__';

export interface AppEventPickerProps {
  appName?: string;
  eventName?: string;
  onChange: (patch: { app_name: string; event_name: string }) => void;
  disabled?: boolean;
  /** Called with true when the user should type the app and event names by hand. */
  onCustomModeChange: (custom: boolean) => void;
}

/**
 * Lists named business events (Event Aliases) by label, grouped by app, so an
 * author picks "Customer purchase" instead of typing an app and event name.
 * Choosing one fills `app_name` and `event_name`. "Something else" falls back
 * to typing both by hand. Shows a loading placeholder while the list loads, and a hint when none exist.
 */
export function AppEventPicker({
  appName,
  eventName,
  onChange,
  disabled,
  onCustomModeChange,
}: AppEventPickerProps) {
  const { aliases, state } = useEventAliases();
  const [custom, setCustom] = useState(false);
  const selectId = useId();

  const grouped = useMemo(() => {
    const groups = new Map<string, EventAliasSummary[]>();
    for (const alias of aliases) {
      groups.set(alias.app, [...(groups.get(alias.app) ?? []), alias]);
    }
    return Array.from(groups.entries());
  }, [aliases]);

  const matched = aliases.find((a) => a.app === appName && a.key === eventName);
  const hasManualValue = Boolean(appName || eventName) && !matched;
  const selectValue = custom || hasManualValue ? CUSTOM_VALUE : matched?.name ?? '';

  useEffect(() => {
    // While loading, keep the typed fields hidden so they do not flash before the list arrives.
    onCustomModeChange(state === 'loading' ? false : aliases.length === 0 || custom || hasManualValue);
  }, [state, aliases.length, custom, hasManualValue, onCustomModeChange]);

  if (state === 'loading') {
    return (
      <div className="space-y-1.5" aria-busy="true">
        <Label>Business event</Label>
        <div className="h-9 animate-pulse rounded-md border bg-muted" />
      </div>
    );
  }
  if (state === 'error') return <AliasLoadError />;
  if (aliases.length === 0) return <EmptyAliasHint canManage />;

  const switchTo = (alias: EventAliasSummary) => {
    setCustom(false);
    onChange({ app_name: alias.app, event_name: alias.key });
  };

  const handleSelect = (value: string) => {
    if (value === CUSTOM_VALUE) {
      setCustom(true);
      return;
    }
    const alias = aliases.find((a) => a.name === value);
    if (!alias) return;
    setCustom(false);
    onChange({ app_name: alias.app, event_name: alias.key });
  };

  return (
    <div className="space-y-1.5">
      <Label htmlFor={selectId}>Business event</Label>
      <Select onValueChange={handleSelect} value={selectValue} disabled={disabled}>
        <SelectTrigger id={selectId} aria-label="Business event">
          <SelectValue placeholder="Choose an event" />
        </SelectTrigger>
        <SelectContent>
          {grouped.map(([app, rows]) => (
            <SelectGroup key={app}>
              <SelectLabel>{app}</SelectLabel>
              {rows.map((alias) => (
                <SelectItem key={alias.name} value={alias.name}>
                  {alias.label}
                  {alias.status === 'Deprecated' ? ' (being phased out)' : ''}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
          <SelectItem value={CUSTOM_VALUE}>Something else (type it in)</SelectItem>
        </SelectContent>
      </Select>
      <p className="text-xs text-steel-soft">
        {matched?.description ||
          'Pick the event that should start this automation. Events are grouped by the app that reports them.'}
      </p>
      <AliasStatusNotice
        appName={appName}
        eventName={eventName}
        aliases={aliases}
        deliberateCustom={custom}
        disabled={disabled}
        onSwitch={switchTo}
      />
    </div>
  );
}
