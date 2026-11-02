import { AlertTriangle, Loader2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { DialogScrollBody, DialogScrollContent, DialogScrollFooter, DialogScrollHeader } from '@/components/ui/dialog-scroll';
import { Button } from '@/components/ui/button';
import { CopyField } from '@/components/ui/copy-field';
import { connectPath, integrationForTool, toolLabel, useIntegrationStatus } from '@/lib/flow/flowIntegrations';
import { startSummary } from '@/lib/flow-list/flowPublishSummary';
import type { TriggerConfig } from '@/types/flow.types';

export interface PublishProblem {
  /** The step's title. */
  title: string;
  message: string;
}

interface PublishFlowDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  flowId: string;
  flowName: string;
  trigger: TriggerConfig | undefined;
  /** Steps of the flow (only their tool settings are read, to spot an integration that is not connected). */
  steps: Array<{ data: { label?: string; actionConfig?: unknown } }>;
  /** Steps that are not finished or have a problem. */
  problems: PublishProblem[];
  publishing: boolean;
  onConfirm: () => void;
}

/**
 * Asked before a flow goes live: what will start it (with the web address and a Copy button for a webhook),
 * anything that will fail or is not finished, and one clear confirm. Publishing never happens silently.
 */
export function PublishFlowDialog({
  open, onOpenChange, flowId, flowName, trigger, steps, problems, publishing, onConfirm,
}: PublishFlowDialogProps) {
  const status = useIntegrationStatus();
  const start = startSummary(trigger, flowId, window.location.origin);

  const unconnected = steps.flatMap((n) => {
    const cfg = n.data.actionConfig as { type?: string; tool_id?: string } | undefined;
    if (cfg?.type !== 'tool-call') return [];
    const service = integrationForTool(cfg.tool_id);
    if (!service || !status[service] || status[service].connected) return [];
    return [{ title: n.data.label || toolLabel(cfg.tool_id), service, label: status[service].label }];
  });
  const hasWarnings = unconnected.length > 0 || problems.length > 0 || start.kind === 'none';

  return (
    <Dialog open={open} onOpenChange={(next) => !publishing && onOpenChange(next)}>
      <DialogScrollContent
        className="sm:max-w-[500px]"
        data-testid="flow-publish-dialog"
        // The web address box would otherwise grab focus and show its text as selected; leave focus on the dialog.
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <DialogScrollHeader>
          <DialogTitle>Publish this flow?</DialogTitle>
          <DialogDescription className="break-words" title={flowName}>
            <span className="line-clamp-2">{flowName}</span>
          </DialogDescription>
        </DialogScrollHeader>
        <DialogScrollBody className="grid gap-4 py-4">
          <div className="grid gap-2" data-testid="flow-publish-summary" data-start-kind={start.kind}>
            <p className="text-sm text-foreground">
              {start.kind === 'none' ? 'Nothing starts this flow yet' : <>This flow will start <strong className="font-semibold">{start.text}</strong>{start.url ? ':' : '.'}</>}
            </p>
            {start.url && (
              <>
                <CopyField label="Web address" value={start.url} />
                <p className="text-meta text-muted-foreground">
                  Anyone calling it needs this flow's secret. You can see it in the Webhook step.
                </p>
              </>
            )}
            <p className="text-meta text-muted-foreground">
              Once it is live, every start runs the steps for real. You can unpublish at any time.
            </p>
          </div>

          {hasWarnings && (
            <div className="grid gap-2 rounded-lg border border-warning/40 bg-warning-tint p-3" role="alert" data-testid="flow-publish-warnings">
              <p className="flex items-center gap-2 text-sm font-medium text-foreground">
                <AlertTriangle className="h-4 w-4 shrink-0 text-warning" aria-hidden />
                Check before you publish
              </p>
              <ul className="grid gap-1.5 text-sm text-muted-foreground">
                {start.kind === 'none' && <li>Nothing is set to start this flow yet.</li>}
                {unconnected.map((u, i) => (
                  <li key={`c${i}`} data-testid="flow-publish-warning-unconnected">
                    <strong className="font-medium text-foreground">{u.title}</strong> will fail until {u.label} is connected.{' '}
                    <Link to={connectPath(u.service)} className="underline underline-offset-2" data-testid="flow-publish-connect">
                      Connect {u.label}
                    </Link>
                  </li>
                ))}
                {problems.map((p, i) => (
                  <li key={`p${i}`} data-testid="flow-publish-warning-problem">
                    <strong className="font-medium text-foreground">{p.title}</strong>: {p.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </DialogScrollBody>
        <DialogScrollFooter className="justify-end">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={publishing} data-testid="flow-publish-cancel">
            Cancel
          </Button>
          <Button size="sm" className="gap-2" onClick={onConfirm} disabled={publishing} data-testid="flow-publish-confirm">
            {publishing && <Loader2 className="h-4 w-4 animate-spin" />}
            {hasWarnings ? 'Publish anyway' : 'Publish'}
          </Button>
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
