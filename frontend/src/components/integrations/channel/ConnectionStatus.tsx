import { Badge } from '@/components/ui/badge';
import type { GatewayDoc } from '@/services/gatewayApi';
import { cn } from '@/lib/utils';

const TONES: Record<string, string> = {
  Connected: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  Degraded: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300',
  Disconnected: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

/** Read-only connection state, the reason for it, and the last error. */
export function ConnectionStatus({ gateway }: { gateway: GatewayDoc }) {
  const state = gateway.connection_state;
  if (!state && !gateway.last_error) return null;
  return (
    <div className="space-y-1.5 rounded-lg border p-4" aria-label="Connection status">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium">Connection</p>
        {state && (
          <Badge variant="secondary" className={cn('border-transparent', TONES[state])}>
            {state}
          </Badge>
        )}
      </div>
      {gateway.connection_reason && <p className="text-xs text-muted-foreground">{gateway.connection_reason}</p>}
      {gateway.last_error && <p className="text-xs text-destructive">Last error: {gateway.last_error}</p>}
    </div>
  );
}
