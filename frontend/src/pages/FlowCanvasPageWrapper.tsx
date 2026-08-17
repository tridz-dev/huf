import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { FlowCanvasPage } from './FlowCanvasPage';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { FlowsHeaderActions, FlowToolbarTitle } from '../components/FlowsHeaderActions';
import { FlowsSidebarContent } from '../components/FlowsSidebarContent';
import { useFlowContext } from '../contexts/FlowContext';

export { FlowCanvasPageWrapper };
export default FlowCanvasPageWrapper;

function FlowCanvasPageWrapper() {
  const { flowId } = useParams<{ flowId: string }>();
  const { setActiveFlow } = useFlowContext();

  useEffect(() => {
    if (flowId) {
      setActiveFlow(flowId);
    }
  }, [flowId, setActiveFlow]);

  return (
    <UnifiedLayout
      compact
      sidebarContent={<FlowsSidebarContent />}
      headerActions={<FlowsHeaderActions />}
      leftContent={<FlowToolbarTitle />}
    >
      <FlowCanvasPage />
    </UnifiedLayout>
  );
}
