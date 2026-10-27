import { Link } from 'react-router-dom';
import { MonitorOff, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatLastSeen, type DesktopRunError } from '@/services/desktopHostApi';

interface DesktopRunBannerProps {
  error: DesktopRunError;
  /** Name of the agent running the conversation (for the "enable on the agent" link). */
  agentName?: string;
  /** True while a retry or rebind is in flight. */
  busy?: boolean;
  /** An extra line under the message, e.g. the reason a rebind was refused. */
  note?: string | null;
  onRetry: () => void;
  onRebind: () => void;
  onDismiss: () => void;
}

/**
 * Shown above the composer when a run in a desktop-hosted conversation was declined before it
 * started. Nothing was created on the server, so the typed message is back in the box and Retry
 * sends it again.
 */
export function DesktopRunBanner({
  error,
  agentName,
  busy = false,
  note,
  onRetry,
  onRebind,
  onDismiss,
}: DesktopRunBannerProps) {
  const label = error.hostLabel || 'The desktop';
  let title: string;
  let body: React.ReactNode;

  switch (error.code) {
    case 'desktop_offline':
      title = `${label} is offline`;
      body = (
        <>
          Last seen {formatLastSeen(error.lastSeen)}. This conversation runs only on that computer, so it
          continues when Huf Desktop is back online.
        </>
      );
      break;
    case 'workspace_changed':
      title = 'The desktop has a different workspace open';
      body = (
        <>
          This conversation belongs to another workspace. Rebind it to the workspace that is open now to
          continue here.
        </>
      );
      break;
    case 'remote_disabled':
      if (error.disabledBy === 'agent') {
        title = 'This agent does not allow remote control';
        body = (
          <>
            Turn on &ldquo;Allow remote desktop control&rdquo; in the{' '}
            {agentName ? (
              <Link to={`/agents/${encodeURIComponent(agentName)}#permissions`} className="underline">
                agent&apos;s permissions
              </Link>
            ) : (
              'agent’s permissions'
            )}
            , then retry.
          </>
        );
      } else {
        title = 'Remote control is off on the desktop';
        body = <>Turn on remote control in Huf Desktop, then retry.</>;
      }
      break;
    case 'permission_denied':
    default:
      title = 'This conversation cannot be run from here';
      body = <>{error.message}</>;
      break;
  }

  const canRetry = error.code !== 'permission_denied';

  return (
    <div
      role="alert"
      data-testid="desktop-run-banner"
      data-code={error.code}
      className="mb-2 flex items-start gap-2.5 rounded-[2px] border border-line bg-paper-deep px-3 py-2.5 text-[13px] text-ink"
    >
      <MonitorOff className="mt-0.5 size-4 flex-none text-steel" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{title}</p>
        <p className="mt-0.5 text-steel">{body}</p>
        {note && <p className="mt-1 text-signal-ink">{note}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {error.code === 'workspace_changed' ? (
            <Button type="button" size="sm" className="h-7 text-xs" disabled={busy} onClick={onRebind}>
              Rebind and retry
            </Button>
          ) : (
            canRetry && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1.5 text-xs"
                disabled={busy}
                onClick={onRetry}
              >
                <RefreshCw className="size-3.5" aria-hidden="true" />
                Retry
              </Button>
            )
          )}
          <Button type="button" variant="ghost" size="sm" className="h-7 text-xs" onClick={onDismiss}>
            Dismiss
          </Button>
        </div>
      </div>
    </div>
  );
}
