import { Shimmer } from '@/components/ai-elements/shimmer';

/** Shown between pressing Stop and the server confirming the run has ended. */
export function StoppingIndicator() {
  return (
    <div role="status" className="py-2">
      <Shimmer className="text-sm text-muted-foreground">Stopping...</Shimmer>
    </div>
  );
}
