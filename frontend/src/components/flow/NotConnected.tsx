import { Link } from 'react-router-dom';
import { Plug } from 'lucide-react';
import { connectPath, integrationForTool, isToolUnconnected, useIntegrationStatus } from '@/lib/flowIntegrations';

/**
 * "Not connected" badge + Connect link for a step whose integration has no credentials.
 * Renders nothing for other steps, or while the connection state is unknown.
 */
export function NotConnected({ toolId, compact, testIdSuffix }: { toolId?: string; compact?: boolean; testIdSuffix: string }) {
  const status = useIntegrationStatus();
  const service = integrationForTool(toolId);
  if (!service || !isToolUnconnected(toolId, status)) return null;
  const name = status[service]?.label ?? service;
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5" data-testid={`flow-not-connected-${testIdSuffix}`}>
      <span className="inline-flex items-center gap-1 rounded bg-signal/10 px-1.5 py-0.5 text-[11px] font-medium text-signal-ink">
        <Plug className="w-3 h-3" aria-hidden />
        Not connected
      </span>
      <Link
        to={connectPath(service)}
        className="text-[11px] text-primary underline-offset-2 hover:underline"
        data-testid={`flow-connect-link-${testIdSuffix}`}
        aria-label={`Connect ${name}`}
        onClick={(e) => e.stopPropagation()}
      >
        {compact ? 'Connect' : `Connect ${name}`}
      </Link>
    </div>
  );
}
