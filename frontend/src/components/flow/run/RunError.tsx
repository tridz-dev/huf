import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { connectPath, notConnectedService } from '@/lib/flow/flowIntegrations';
import { notConnectedName } from '@/lib/flow-run/story/headline';

interface RunErrorProps {
  /** The reason, already in plain words. */
  reason: string;
  /** The failed step; without one (the run itself failed) there is no step to open. */
  stepId?: string;
  /** May edit the flow: "Fix this step" and "Connect ...". Others only get "Open this step". */
  canManage: boolean;
  onOpenStep?: (id: string) => void;
}

/** The one error of a failed run: a plain message and the way to fix it. */
export function RunError({ reason, stepId, canManage, onOpenStep }: RunErrorProps) {
  const service = canManage ? notConnectedService(reason) : undefined;
  const name = notConnectedName(reason);
  const providers = canManage && /\bAI Providers\b/.test(reason);
  return (
    <div className="mt-2 rounded-r-md border-l-2 border-destructive bg-destructive/5 px-3 py-2" data-testid="flow-run-error">
      <p className="text-sm text-ink" data-testid={stepId ? `flow-run-step-error-${stepId}` : 'flow-run-error-text'}>{reason}</p>
      {(stepId || service || providers) && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {stepId && onOpenStep && (
            <Button type="button" size="sm" variant="outline" className="max-[1023px]:min-h-11" data-testid={`flow-run-fix-${stepId}`} onClick={() => onOpenStep(stepId)}>
              {canManage ? 'Fix this step' : 'Open this step'}
            </Button>
          )}
          {providers && (
            <Button asChild size="sm" variant="outline" className="max-[1023px]:min-h-11">
              <Link to="/providers" data-testid="flow-run-open-providers">Open AI Providers</Link>
            </Button>
          )}
          {service && (
            <Button asChild size="sm" variant="outline" className="max-[1023px]:min-h-11">
              <Link to={connectPath(service)} data-testid={stepId ? `flow-run-step-connect-${stepId}` : 'flow-run-connect'}>Connect {name ?? 'it'}</Link>
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
