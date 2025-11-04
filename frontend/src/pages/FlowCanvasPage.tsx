import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { FlowCanvas } from '../components/FlowCanvas';
import { RightSidebar } from '../components/RightSidebar';
import { useFlowContext } from '../contexts/FlowContext';

export function FlowCanvasPage() {
  const { flowId } = useParams<{ flowId: string }>();
  const navigate = useNavigate();
  const { setActiveFlow, activeFlow } = useFlowContext();
  const [showRightSidebar, setShowRightSidebar] = useState(true);

  useEffect(() => {
    if (flowId) {
      setActiveFlow(flowId);
    } else {
      navigate('/flows');
    }
  }, [flowId, setActiveFlow, navigate]);

  if (!activeFlow) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <div className="text-center">
          <div className="text-muted-foreground mb-2">Loading flow...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full overflow-hidden">
      <div className="flex-1 flex overflow-hidden">
        <FlowCanvas
          showLeftSidebar={true}
          showRightSidebar={showRightSidebar}
          onToggleLeftSidebar={() => {}}
          onToggleRightSidebar={() => setShowRightSidebar(!showRightSidebar)}
        />
        {showRightSidebar && <RightSidebar onToggle={() => setShowRightSidebar(false)} />}
      </div>
    </div>
  );
}
