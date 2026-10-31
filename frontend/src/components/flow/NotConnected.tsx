import { Link } from 'react-router-dom';
import { Plug } from 'lucide-react';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { connectPath, integrationForTool, isToolUnconnected, useIntegrationStatus } from '@/lib/flow/flowIntegrations';

/**
 * "Not connected" badge + Connect link for a step whose integration has no credentials.
 * Renders nothing for other steps, or while the connection state is unknown.
 */
export function NotConnected({ toolId, compact, testIdSuffix }: { toolId?: string; compact?: boolean; testIdSuffix: string }) {
  const status = useIntegrationStatus();
  const { canManage } = useFlowPermissions();
  const service = integrationForTool(toolId);
  if (!service || !isToolUnconnected(toolId, status)) return null;
  const name = status[service]?.label ?? service;
  // Connecting changes the account's integrations: people who cannot edit the flow only learn that it is not connected.
  if (!canManage) {
    return (
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5" data-testid={`flow-not-connected-${testIdSuffix}`}>
        <span className="inline-flex items-center gap-1 rounded bg-signal/10 px-1.5 py-0.5 text-meta font-medium text-signal-ink">
          <Plug className="w-3 h-3" aria-hidden />
          Not connected
        </span>
        {!compact && (
          <span className="text-meta text-muted-foreground" data-testid={`flow-not-connected-note-${testIdSuffix}`}>
            A flow editor needs to connect {name}.
          </span>
        )}
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5" data-testid={`flow-not-connected-${testIdSuffix}`}>
      <span className="inline-flex items-center gap-1 rounded bg-signal/10 px-1.5 py-0.5 text-meta font-medium text-signal-ink">
        <Plug className="w-3 h-3" aria-hidden />
        Not connected
      </span>
      <Link
        to={connectPath(service)}
        className="text-meta font-medium text-primary underline underline-offset-2"
        data-testid={`flow-connect-link-${testIdSuffix}`}
        aria-label={`Connect ${name}`}
        onClick={(e) => e.stopPropagation()}
      >
        {compact ? 'Connect' : `Connect ${name}`}
      </Link>
    </div>
  );
}
