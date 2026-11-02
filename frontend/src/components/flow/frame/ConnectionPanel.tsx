import { Link } from 'react-router-dom';
import { CheckCircle2, Plug } from 'lucide-react';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { connectPath, integrationForTool, isToolUnconnected, useIntegrationStatus } from '@/lib/flow/flowIntegrations';
import { Button } from '../../ui/button';

/**
 * The connection a step needs, at the very top of its Setup tab: amber with a Connect button when the account is not
 * connected, a calm "Connected" line when it is. Renders nothing for steps that use no outside account.
 */
export function ConnectionPanel({ toolId }: { toolId?: string }) {
  const status = useIntegrationStatus();
  const { canManage } = useFlowPermissions();
  const service = integrationForTool(toolId);
  if (!service) return null;
  const name = status[service]?.label ?? service;
  const unconnected = isToolUnconnected(toolId, status);
  if (!unconnected) {
    // Only say "Connected" once the state is actually known.
    if (!status[service]) return null;
    return (
      <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs" data-testid="flow-connection-ok">
        <CheckCircle2 className="h-4 w-4 shrink-0 text-good" aria-hidden />
        <span className="min-w-0 flex-1 truncate">{name} is connected</span>
      </div>
    );
  }
  return (
    <div className="space-y-2.5 rounded-md border border-warning/30 bg-warning-tint px-3 py-2.5 text-xs" data-testid="flow-connection-needed">
      <div className="flex items-start gap-2">
        <Plug className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
        <span className="min-w-0 flex-1 font-medium text-warning" data-testid="flow-not-connected-sidebar">
          {canManage ? `Connect ${name} to use this step` : `${name} is not connected`}
        </span>
      </div>
      {canManage ? (
        <Button asChild size="sm" className="w-full" data-testid="flow-connect-link-sidebar">
          <Link to={connectPath(service)} aria-label={`Connect ${name}`}>
            Connect {name}
          </Link>
        </Button>
      ) : (
        <span className="block text-meta text-muted-foreground" data-testid="flow-not-connected-note-sidebar">
          A flow editor needs to connect {name}.
        </span>
      )}
    </div>
  );
}
