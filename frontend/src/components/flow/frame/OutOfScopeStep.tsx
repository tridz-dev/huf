import { X } from 'lucide-react';
import { Button } from '../../ui/button';
import type { FlowNode } from '../../../types/flow.types';

/** The panel of a step the embedded editor does not offer: no field is mounted, so nothing can rewrite its settings. */
export function OutOfScopeStep({ node, onClose }: { node: FlowNode; onClose?: () => void }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="flow-step-out-of-scope">
      <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-border bg-card px-3.5">
        <span className="min-w-0 flex-1 truncate text-ui-text font-semibold">{node.data.label}</span>
        {onClose && (
          <Button type="button" variant="ghost" size="icon" aria-label="Close" onClick={onClose}>
            <X className="h-4 w-4" aria-hidden />
          </Button>
        )}
      </div>
      <p role="status" className="p-3.5 text-sm text-muted-foreground">This step cannot be edited here. It is kept as it is and saved unchanged.</p>
    </div>
  );
}
