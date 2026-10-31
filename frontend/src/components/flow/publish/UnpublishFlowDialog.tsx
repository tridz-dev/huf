import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { startSummary } from '@/lib/flow-list/flowPublishSummary';
import { gatewayStopLine } from '@/lib/flow-gateway/gatewaySummary';
import { peekGatewayRegistry } from '@/lib/flow-gateway/registryStore';
import type { GatewayTriggerUiConfig } from '@/types/flow.types';
import type { TriggerConfig } from '@/types/flow.types';

interface UnpublishFlowDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  flowName: string;
  trigger: TriggerConfig | undefined;
  busy: boolean;
  onConfirm: () => void;
}

/** What turning a live flow off does, and what it does not. */
export function UnpublishFlowDialog({ open, onOpenChange, flowName, trigger, busy, onConfirm }: UnpublishFlowDialogProps) {
  const start = startSummary(trigger, '', '');
  const stops =
    start.kind === 'webhook' ? 'Requests to its web address are refused.'
      : start.kind === 'schedule' ? 'Its schedule stops starting it.'
        : start.kind === 'doc-event' ? 'Record changes stop starting it.'
          : start.kind === 'chat' ? gatewayStopLine(trigger as GatewayTriggerUiConfig, peekGatewayRegistry()?.gateways)
          : 'Nothing starts it by itself any more.';
  return (
    <AlertDialog open={open} onOpenChange={(next) => !busy && onOpenChange(next)}>
      <AlertDialogContent data-testid="flow-unpublish-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>Unpublish this flow?</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="grid gap-2">
              <span className="line-clamp-2 break-words font-medium text-foreground" title={flowName}>{flowName}</span>
              <span>It goes back to a draft. {stops} It can still be run by hand.</span>
              <span>Runs already in progress finish. Nothing is deleted, and you can publish it again at any time.</span>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            data-testid="flow-unpublish-confirm"
            disabled={busy}
            onClick={(e) => {
              e.preventDefault();
              onConfirm();
            }}
          >
            {busy ? 'Unpublishing...' : 'Unpublish'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
