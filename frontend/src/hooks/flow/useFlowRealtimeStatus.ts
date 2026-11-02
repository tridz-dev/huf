import { useEffect, type Dispatch, type SetStateAction } from 'react';
import type { Flow } from '../../types/flow.types';

/** Live per-step status on the canvas, from the flow run realtime events. */
export function useFlowRealtimeStatus(
  activeFlowId: string | null,
  setActiveFlowState: Dispatch<SetStateAction<Flow | null>>,
  refreshFlows: () => void,
) {
  useEffect(() => {
    if (!activeFlowId) return;

    const handleNodeStart = (e: Event) => {
      const data = (e as CustomEvent).detail;
      setActiveFlowState(prev => {
        if (!prev) return prev;
        const nodes = prev.nodes.map(n =>
          n.id === data.node_id ? { ...n, data: { ...n.data, status: 'running' as const } } : n
        );
        return { ...prev, nodes };
      });
    };

    const handleNodeEnd = (e: Event) => {
      const data = (e as CustomEvent).detail;
      setActiveFlowState(prev => {
        if (!prev) return prev;
        const nodes = prev.nodes.map(n =>
          n.id === data.node_id ? { ...n, data: { ...n.data, status: data.status === 'success' ? ('success' as const) : ('error' as const) } } : n
        );
        return { ...prev, nodes };
      });
    };

    const handleFlowPaused = (e: Event) => {
      const data = (e as CustomEvent).detail;
      setActiveFlowState(prev => {
        if (!prev) return prev;
        const nodes = prev.nodes.map(n =>
          n.id === data.node_id ? { ...n, data: { ...n.data, status: 'waiting' as const } } : n
        );
        return { ...prev, nodes };
      });
    };

    const handleFlowCompleted = (e: Event) => {
      const data = (e as CustomEvent).detail;
      setActiveFlowState(prev => {
        if (!prev) return prev;
        // Mark node as success if provided
        const nodes = prev.nodes.map(n =>
          data.node_id && n.id === data.node_id ? { ...n, data: { ...n.data, status: 'success' as const } } : n
        );
        return { ...prev, nodes };
      });
      refreshFlows(); // Reload flows to get updated statuses
    };

    const handleFlowError = (e: Event) => {
      const data = (e as CustomEvent).detail;
      // Mark flow as error
      setActiveFlowState(prev => {
        if (!prev) return prev;
        // Mark the active node as error
        const nodes = prev.nodes.map(n =>
          n.data.status === 'running' || (data.node_id && n.id === data.node_id)
            ? { ...n, data: { ...n.data, status: 'error' as const } }
            : n
        );
        return { ...prev, nodes };
      });
    };

    window.addEventListener('frappe:flow_node_start', handleNodeStart);
    window.addEventListener('frappe:flow_node_end', handleNodeEnd);
    window.addEventListener('frappe:flow_paused', handleFlowPaused);
    window.addEventListener('frappe:flow_completed', handleFlowCompleted);
    window.addEventListener('frappe:flow_error', handleFlowError);

    return () => {
      window.removeEventListener('frappe:flow_node_start', handleNodeStart);
      window.removeEventListener('frappe:flow_node_end', handleNodeEnd);
      window.removeEventListener('frappe:flow_paused', handleFlowPaused);
      window.removeEventListener('frappe:flow_completed', handleFlowCompleted);
      window.removeEventListener('frappe:flow_error', handleFlowError);
    };
  }, [activeFlowId, refreshFlows, setActiveFlowState]);
}
