import { useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { usePageLayout } from '@/hooks/usePageLayout';
import { FlowCanvasPage } from './FlowCanvasPage';
import { FlowsHeaderActions } from '../components/FlowsHeaderActions';
import { useFlowContext } from '../contexts/FlowContext';

export { FlowCanvasPageWrapper };
export default FlowCanvasPageWrapper;

function FlowCanvasPageWrapper() {
  const { flowId } = useParams<{ flowId: string }>();
  const { activeFlow, setActiveFlow } = useFlowContext();

  useEffect(() => {
    if (flowId) {
      setActiveFlow(flowId);
    }
  }, [flowId, setActiveFlow]);

  const breadcrumbs = useMemo(() => {
    return [
      { label: 'Flows', href: '/flows' },
      { label: activeFlow?.name || 'Loading...' },
    ];
  }, [activeFlow]);

  usePageLayout({
    breadcrumbs,
    headerActions: <FlowsHeaderActions />,
  });

  return <FlowCanvasPage />;
}
