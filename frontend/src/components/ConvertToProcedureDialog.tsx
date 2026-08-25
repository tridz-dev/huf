import { useEffect, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from './ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import {
  analyzeFlowConversion,
  convertFlowToProcedure,
  FlowConversionAnalysis,
} from '@/services/flowApi';

interface ConvertToProcedureDialogProps {
  flowId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * "Analyse & Optimize" for a single Flow (T-52): shows whether this flow can become a
 * fixed, deterministic procedure, and if so what it reads/writes and the estimated
 * reduction. Converting always creates a Draft the user still has to review and enable
 * elsewhere -- this dialog never activates anything.
 */
export function ConvertToProcedureDialog({ flowId, open, onOpenChange }: ConvertToProcedureDialogProps) {
  const [loading, setLoading] = useState(false);
  const [converting, setConverting] = useState(false);
  const [analysis, setAnalysis] = useState<FlowConversionAnalysis | null>(null);

  useEffect(() => {
    if (!open) {
      setAnalysis(null);
      return;
    }
    setLoading(true);
    analyzeFlowConversion(flowId)
      .then(setAnalysis)
      .catch(() => setAnalysis(null))
      .finally(() => setLoading(false));
  }, [open, flowId]);

  const handleConvert = async () => {
    setConverting(true);
    try {
      const result = await convertFlowToProcedure(flowId);
      toast.success('Procedure created as a draft', {
        description: `Review "${result.procedure_id}" before enabling it.`,
      });
      onOpenChange(false);
    } catch {
      // handleFrappeError inside convertFlowToProcedure already surfaced this
    } finally {
      setConverting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            Optimization opportunity
          </DialogTitle>
          <DialogDescription>
            Turn this flow into a fixed, deterministic procedure your agents can run directly.
          </DialogDescription>
        </DialogHeader>

        {loading && <div className="py-6 text-sm text-muted-foreground">Checking this flow...</div>}

        {!loading && analysis && !analysis.convertible && (
          <div className="py-2 text-sm text-muted-foreground">{analysis.reason}</div>
        )}

        {!loading && analysis && analysis.convertible && (
          <div className="space-y-3 py-2 text-sm">
            <div>
              <span className="font-medium">Reads: </span>
              {analysis.reads && analysis.reads.length > 0 ? analysis.reads.join(', ') : 'nothing'}
            </div>
            <div>
              <span className="font-medium">Writes: </span>
              {analysis.writes && analysis.writes.length > 0 ? analysis.writes.join(', ') : 'none'}
            </div>
            {typeof analysis.estimated_round_trip_reduction_pct === 'number' &&
              analysis.estimated_round_trip_reduction_pct > 0 && (
                <div className="text-muted-foreground">
                  Estimated {analysis.estimated_round_trip_reduction_pct}% fewer round trips than
                  running this step by step.
                </div>
              )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {analysis?.convertible && (
            <Button onClick={handleConvert} disabled={converting}>
              {converting ? 'Creating draft...' : 'Create draft procedure'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
