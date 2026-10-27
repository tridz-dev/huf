import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useDesktopHosts } from '@/hooks/useDesktopHosts';
import {
  PERMISSION_MODES,
  PERMISSION_MODE_LABELS,
  isPermissionMode,
  permissionModeErrorText,
  setDesktopPermissionMode,
  type PermissionMode,
} from '@/services/desktopHostApi';

interface DesktopPermissionModeControlProps {
  deviceId: string;
}

/**
 * Permission-mode picker for a desktop-hosted conversation's workspace. It reads the desktop's
 * current mode from the host poll, and after a change shows the mode the desktop confirmed (never
 * the one the user asked for), so a refused or partial change is visible rather than optimistic.
 */
export function DesktopPermissionModeControl({ deviceId }: DesktopPermissionModeControlProps) {
  const { byDevice, refresh } = useDesktopHosts(true);
  const host = byDevice.get(deviceId);
  const [pending, setPending] = useState(false);
  // The mode confirmed by the last acknowledged change; cleared when the poll catches up.
  const [applied, setApplied] = useState<PermissionMode | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);

  const polledMode = isPermissionMode(host?.mode) ? host?.mode : null;
  useEffect(() => {
    if (applied && polledMode === applied) setApplied(null);
  }, [applied, polledMode]);

  const online = Boolean(host?.online);
  const remote = Boolean(host?.remote_control);
  const current: PermissionMode | null = applied ?? polledMode;

  let disabledReason: string | null = null;
  if (!host || !online) disabledReason = 'The desktop is offline.';
  else if (!remote) disabledReason = 'Remote control is off on this desktop.';

  async function change(next: string) {
    if (!isPermissionMode(next) || pending || next === current) return;
    setPending(true);
    setErrorText(null);
    try {
      const result = await setDesktopPermissionMode(deviceId, next);
      if (result.ok) {
        const confirmed = isPermissionMode(result.appliedMode) ? result.appliedMode : next;
        setApplied(confirmed);
        toast.success(`Permission mode is now ${PERMISSION_MODE_LABELS[confirmed]}`);
      } else if (result.error) {
        const text = permissionModeErrorText(result.error);
        setErrorText(text);
        if (isPermissionMode(result.error.appliedMode)) setApplied(result.error.appliedMode);
        toast.error('Permission mode not changed', { description: text });
      }
    } catch (err) {
      const text = err instanceof Error ? err.message : 'The permission mode could not be changed.';
      setErrorText(text);
      toast.error('Permission mode not changed', { description: text });
    } finally {
      setPending(false);
      void refresh();
    }
  }

  return (
    <div className="flex min-w-0 items-center gap-2" data-testid="desktop-permission-mode">
      <Select value={current ?? undefined} onValueChange={change} disabled={Boolean(disabledReason) || pending}>
        <SelectTrigger
          aria-label="Permission mode"
          title={disabledReason ?? 'Permission mode on the desktop'}
          className="h-7 w-[110px] gap-1 px-2 text-[12px]"
        >
          <SelectValue placeholder={pending ? 'Applying' : 'Mode'} />
        </SelectTrigger>
        <SelectContent>
          {PERMISSION_MODES.map((mode) => (
            <SelectItem key={mode} value={mode} className="text-[13px]">
              {PERMISSION_MODE_LABELS[mode]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {errorText && (
        <span role="alert" className="max-w-[260px] truncate text-[11px] text-signal-ink" title={errorText}>
          {errorText}
        </span>
      )}
    </div>
  );
}
