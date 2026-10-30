import { EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Says a run is drawn on the canvas (step colours, what each step produced on hover, the way the run went) and lets the
 * person take the colours away again.
 */
export function RunOverlayChip({ onHide }: { onHide: () => void }) {
  return (
    <div className="flex items-center gap-1 rounded-lg border border-line bg-panel py-1 pl-3 pr-1 text-xs text-ink shadow-sm" data-testid="flow-run-overlay-chip" title="Each step shows how this run went. Hover a step to see what it did.">
      <span>Showing this run</span>
      <Button variant="ghost" size="sm" className="gap-1 px-2 text-xs" onClick={onHide} data-testid="flow-run-overlay-hide">
        <EyeOff className="h-3.5 w-3.5" aria-hidden />
        Hide
      </Button>
    </div>
  );
}
