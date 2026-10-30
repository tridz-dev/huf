import type { FlowNode } from '../../../types/flow.types';
import { StepTestPanel } from '../test/StepTestPanel';

/**
 * The Test tab of the step panel: try the step on its own with sample data and pin what it produced (UX-16).
 * The body lives in `components/flow/test/`.
 */
export function StepTestTab({ node, active, onOpenSetup }: { node: FlowNode; active: boolean; onOpenSetup: () => void }) {
  return <StepTestPanel node={node} active={active} onOpenSetup={onOpenSetup} />;
}
