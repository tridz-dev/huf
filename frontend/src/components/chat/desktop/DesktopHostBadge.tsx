import { Monitor } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useDesktopHosts } from '@/hooks/useDesktopHosts';
import type { DesktopHostRef } from '@/services/chatApi';

interface DesktopHostBadgeProps {
  host: DesktopHostRef;
  /** Icon and dot only, for dense lists. The label moves to the tooltip and screen readers. */
  compact?: boolean;
  className?: string;
}

/** Status dot: green online, grey offline, hollow while the first poll is still loading. */
export function HostStatusDot({ online, className }: { online: boolean | undefined; className?: string }) {
  return (
    <span
      aria-hidden="true"
      data-testid="host-status-dot"
      data-online={online === undefined ? 'unknown' : String(online)}
      className={cn(
        'inline-block size-1.5 flex-none rounded-full',
        online === true && 'bg-good',
        online === false && 'bg-steel-soft',
        online === undefined && 'border border-steel-soft',
        className,
      )}
    />
  );
}

/**
 * Where a desktop-hosted conversation runs: computer and workspace, with a live online dot.
 * The online state comes from the shared `list_desktop_hosts` poll, so many badges cost one request.
 */
export function DesktopHostBadge({ host, compact = false, className }: DesktopHostBadgeProps) {
  const { byDevice, loaded } = useDesktopHosts(true);
  const info = byDevice.get(host.deviceId);
  const online: boolean | undefined = loaded ? Boolean(info?.online) : undefined;
  const label = host.label || info?.label || 'Desktop';
  const stateText = online === undefined ? 'checking' : online ? 'online' : 'offline';
  const title = `Runs on ${label} (${stateText})`;

  return (
    <span
      title={title}
      data-testid="desktop-host-badge"
      className={cn('inline-flex min-w-0 items-center gap-1.5 text-steel', className)}
    >
      <Monitor className="size-3.5 flex-none" aria-hidden="true" />
      <HostStatusDot online={online} />
      {compact ? (
        <span className="sr-only">{title}</span>
      ) : (
        <>
          <span className="truncate font-mono text-[11px] text-steel">{label}</span>
          <span className="sr-only">{stateText}</span>
        </>
      )}
    </span>
  );
}
