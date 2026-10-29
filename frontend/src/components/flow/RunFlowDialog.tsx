import { useEffect, useState } from 'react';
import { Loader2, Play } from 'lucide-react';
import { Dialog, DialogDescription, DialogTitle } from '../ui/dialog';
import { DialogScrollBody, DialogScrollContent, DialogScrollFooter, DialogScrollHeader } from '../ui/dialog-scroll';
import { Textarea } from '../ui/textarea';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { parsePayload, readLastPayload, rememberPayload } from '@/lib/flowRunPayload';

interface RunFlowDialogProps {
  open: boolean;
  flowId: string | null;
  flowName?: string;
  onOpenChange: (open: boolean) => void;
  /** Starts the run with the parsed payload. Resolve when the run has been reported. */
  onRun: (payload: Record<string, unknown>) => Promise<void>;
}

export function RunFlowDialog({ open, flowId, flowName, onOpenChange, onRun }: RunFlowDialogProps) {
  const [text, setText] = useState('{}');
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (open && flowId) {
      setText(readLastPayload(flowId));
      setError(null);
    }
  }, [open, flowId]);

  const handleChange = (value: string) => {
    setText(value);
    setError(parsePayload(value).error);
  };

  const handleRun = async () => {
    if (!flowId) return;
    const parsed = parsePayload(text);
    if (parsed.error || !parsed.value) {
      setError(parsed.error);
      return;
    }
    setRunning(true);
    try {
      rememberPayload(flowId, text);
      await onRun(parsed.value);
      onOpenChange(false);
    } finally {
      setRunning(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !running && onOpenChange(next)}>
      <DialogScrollContent className="sm:max-w-[520px]" data-testid="flow-run-dialog">
        <DialogScrollHeader>
          <DialogTitle>Run {flowName ? `"${flowName}"` : 'flow'}</DialogTitle>
          <DialogDescription>
            Starts the flow once, right now, as if its trigger had fired. This is a real run: emails are sent and records are created.
          </DialogDescription>
        </DialogScrollHeader>
        <DialogScrollBody className="grid gap-2 py-4">
          <Label htmlFor="flow-run-payload">Input data (JSON)</Label>
          <Textarea
            id="flow-run-payload"
            data-testid="flow-run-payload"
            className="min-h-[160px] font-mono text-xs"
            spellCheck={false}
            value={text}
            aria-invalid={!!error}
            onChange={(event) => handleChange(event.target.value)}
          />
          {error ? (
            <p role="alert" data-testid="flow-run-payload-error" className="text-sm text-destructive">
              {error}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground" data-testid="flow-run-payload-hint">
              This is the data the trigger would hand to the flow. Steps read it as input, for example {'{"name": "Ada"}'} is available as input.name.
              Leave it as {'{}'} to run without input. When the run finishes, find it under Runs.
            </p>
          )}
        </DialogScrollBody>
        <DialogScrollFooter>
          <Button variant="outline" size="sm" data-testid="flow-run-cancel" onClick={() => onOpenChange(false)} disabled={running}>
            Cancel
          </Button>
          <Button size="sm" className="gap-2" data-testid="flow-run-start" onClick={handleRun} disabled={running || !!error}>
            {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            Run flow
          </Button>
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
