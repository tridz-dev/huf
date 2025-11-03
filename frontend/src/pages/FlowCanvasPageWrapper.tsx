import { useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { FlowCanvasPage } from './FlowCanvasPage';
import { UnifiedLayout, BreadcrumbItem } from '../layouts/UnifiedLayout';
import { FlowsHeaderActions } from '../components/FlowsHeaderActions';
import { FlowsSidebarContent } from '../components/FlowsSidebarContent';
import { useFlowContext } from '../contexts/FlowContext';

export function FlowCanvasPageWrapper() {
  const { flowId } = useParams<{ flowId: string }>();
  const { activeFlow, setActiveFlow } = useFlowContext();

  useEffect(() => {
    if (flowId) {
      setActiveFlow(flowId);
    }
  }, [flowId, setActiveFlow]);

  const breadcrumbs: BreadcrumbItem[] = useMemo(() => {
    return [
      { label: 'Flows', href: '/flows' },
      { label: activeFlow?.name || 'Loading...' },
    ];
  }, [activeFlow]);

  return (
    <UnifiedLayout
      sidebarContent={<FlowsSidebarContent />}
      headerActions={<FlowsHeaderActions />}
      breadcrumbs={breadcrumbs}
    >
      <FlowCanvasPage />
    </UnifiedLayout>
  );
}
