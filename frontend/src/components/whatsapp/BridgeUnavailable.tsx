import { PlugZap } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { useIsHufAdmin } from '@/contexts/PermissionsContext';
import { Button } from '@/components/ui/button';

export const CONNECTOR_NEEDED = 'Template management and message history need the WhatsApp Business connector app';

export function BridgeUnavailable() {
  return (
    <div role="status" className="flex flex-col items-center gap-2 rounded-sm border border-line p-10 text-center">
      <PlugZap className="h-6 w-6 text-steel" />
      <h3 className="text-sm font-semibold text-ink">WhatsApp Business connector not installed</h3>
      <p className="max-w-md text-xs text-steel">
        {CONNECTOR_NEEDED}. Install it on this site, then reload. Ask your administrator if you are unsure how.
      </p>
    </div>
  );
}

/** Server exceptions (tracebacks, SQL errors) are not something a user can act on. */
const TECHNICAL = /(Error\b|Exception|Traceback|\bSELECT\b|\bUnknown column\b|\(\d{4},|\bat \S+\.py)/;

export function isTechnicalMessage(message: string): boolean {
  return TECHNICAL.test(message) || message.length > 300;
}

export function LoadError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const technical = isTechnicalMessage(message);
  const isAdmin = useIsHufAdmin();
  return (
    <Alert variant="destructive" role="alert">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          <AlertDescription>
            {technical ? 'Something went wrong while loading this page. Try again; if it keeps happening, ask your administrator.' : message}
          </AlertDescription>
          {technical && isAdmin && (
            <Collapsible>
              <CollapsibleTrigger className="text-xs underline">Technical details</CollapsibleTrigger>
              <CollapsibleContent>
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all text-[11px]">{message}</pre>
              </CollapsibleContent>
            </Collapsible>
          )}
        </div>
        {onRetry && (
          <Button type="button" size="sm" variant="outline" onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    </Alert>
  );
}
