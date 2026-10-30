import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useFlowContext } from '@/contexts/FlowContext';

/**
 * `?step=<step id>` opens that step in the editor (the run page's "Fix this step" link when the editor was not open).
 * The step is selected once the flow has loaded and the parameter is removed, so a reload does not select it again.
 */
export function useStepParam(): void {
  const { activeFlow, setSelectedNode } = useFlowContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const step = searchParams.get('step');
  const known = !!step && !!activeFlow?.nodes.some((n) => n.id === step);
  useEffect(() => {
    if (!step || !known) return;
    setSelectedNode(step);
    setSearchParams((prev) => {
      const sp = new URLSearchParams(prev);
      sp.delete('step');
      return sp;
    }, { replace: true });
  }, [step, known, setSelectedNode, setSearchParams]);
}
