import type { EventAliasSummary } from '@/services/automationApi';
import { Button } from '@/components/ui/button';

const ALIAS_DESK_PATH = '/app/event-alias';

/** Shown when no business events are defined yet. Links to where they are managed. */
export function EmptyAliasHint({ canManage }: { canManage: boolean }) {
  return (
    <p className="text-xs text-steel-soft">
      No business events are set up yet, so type the app and event names below.
      {canManage && (
        <>
          {' '}
          <a className="underline" href={ALIAS_DESK_PATH} target="_blank" rel="noreferrer">
            Manage business events
          </a>
        </>
      )}
    </p>
  );
}

export function AliasLoadError() {
  return (
    <p role="alert" className="text-xs text-warning">
      Could not load business events. Type the app and event names below.
    </p>
  );
}

interface AliasStatusNoticeProps {
  appName?: string;
  eventName?: string;
  aliases: EventAliasSummary[];
  /** True when the author chose "Something else" on purpose in this session. */
  deliberateCustom: boolean;
  disabled?: boolean;
  onSwitch: (alias: EventAliasSummary) => void;
}

/**
 * Warns when the saved event is phased out or no longer defined. Never rewrites
 * the trigger on its own: switching to the replacement is an explicit button.
 */
export function AliasStatusNotice({
  appName,
  eventName,
  aliases,
  deliberateCustom,
  disabled,
  onSwitch,
}: AliasStatusNoticeProps) {
  if (!appName || !eventName) return null;
  const matched = aliases.find((a) => a.app === appName && a.key === eventName);

  if (!matched) {
    if (deliberateCustom) return null;
    return (
      <p role="status" className="text-xs text-warning">
        &quot;{appName} / {eventName}&quot; is not in the list of business events. It may have been
        renamed or removed, so this automation might never fire. Pick a current event, or keep it if
        your app reports it another way.
      </p>
    );
  }

  if (matched.status !== 'Deprecated') return null;
  const replacement = aliases.find((a) => a.name === matched.replaced_by && a.status !== 'Deprecated');
  return (
    <div role="status" className="space-y-1.5 text-xs text-warning">
      <p>
        &quot;{matched.label}&quot; is being phased out
        {replacement ? `. Use "${replacement.label}" instead.` : ' and has no replacement yet.'}
      </p>
      {replacement && (
        <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => onSwitch(replacement)}>
          Switch to {replacement.label}
        </Button>
      )}
    </div>
  );
}

/** Reminder that App Event triggers do nothing until the automation is active. */
export function DraftAutomationNotice() {
  return (
    <p role="status" className="text-xs text-warning">
      This automation is a draft. Business events will not start it until you activate it
      {' '}after saving.
    </p>
  );
}
