import { FlaskConical } from 'lucide-react';
import { Button } from '../../ui/button';
import { Label } from '../../ui/label';
import { Textarea } from '../../ui/textarea';
import { DisabledReason } from '../DisabledReason';

/**
 * The Test tab. Testing one step on its own (sample input, "Test step", the output, "Pin this output") is built by
 * UX-16; until then this is a clean placeholder that says so and keeps the layout those controls will fill.
 * UX-16 replaces `StepTestPlaceholder` with the real panel and nothing else in the frame needs to change.
 */
export function StepTestPlaceholder({ isTrigger }: { nodeId: string; isTrigger: boolean }) {
  return (
    <div className="space-y-4" data-testid="flow-step-test-placeholder">
      <div className="flex items-start gap-3 rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
        <FlaskConical className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <p>
          {isTrigger
            ? 'Soon you will be able to send a sample request here and see the data this flow starts with.'
            : 'Soon you will be able to try just this step with sample data and see what it does, without running the whole flow.'}
        </p>
      </div>
      <div>
        <Label htmlFor="step-test-sample" size="sm">Sample input</Label>
        <Textarea
          id="step-test-sample"
          data-testid="flow-step-test-sample"
          disabled
          placeholder="The data this step receives will show here."
          className="mt-1 min-h-24"
        />
      </div>
      <DisabledReason reason="Coming soon: testing one step on its own.">
        <Button type="button" variant="outline" className="w-full" data-testid="flow-step-test-run" disabled>
          Test step
        </Button>
      </DisabledReason>
    </div>
  );
}
