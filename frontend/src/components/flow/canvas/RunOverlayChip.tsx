import { Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Says a run is drawn on the canvas (step colours, what each step produced on hover, the way the run went) and lets the
 * person turn the colours off and on again without closing the run.
 */
export function RunOverlayChip({ hidden, onToggle }: { hidden: boolean; onToggle: () => void }) {
  return (
    <div
      className="flex items-center gap-1 rounded-lg border border-line bg-panel py-1 pl-3 pr-1 text-xs text-ink shadow-sm"
      data-testid="flow-run-overlay-chip"
      data-shown={hidden ? 'false' : 'true'}
    >
      <span>{hidden ? 'Run colours are off' : 'Showing how this run went'}</span>
      <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs" onClick={onToggle} data-testid="flow-run-overlay-toggle" aria-pressed={!hidden}>
        {hidden ? <Eye className="h-3.5 w-3.5" aria-hidden /> : <EyeOff className="h-3.5 w-3.5" aria-hidden />}
        {hidden ? 'Show' : 'Hide'}
      </Button>
    </div>
  );
}
