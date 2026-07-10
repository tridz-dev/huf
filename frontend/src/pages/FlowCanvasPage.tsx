import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Settings2 } from 'lucide-react';
import { FlowCanvas } from '../components/FlowCanvas';
import { RightSidebar } from '../components/RightSidebar';
import { useFlowContext } from '../contexts/FlowContext';
import { useIsMobile } from '@/hooks/use-mobile';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';

export function FlowCanvasPage() {
  const { flowId } = useParams<{ flowId: string }>();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const { setActiveFlow, activeFlow, selectedNodeId, selectedEdgeId } = useFlowContext();
  const [showRightSidebar, setShowRightSidebar] = useState(true);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  useEffect(() => {
    if (flowId) {
      setActiveFlow(flowId);
    } else {
      navigate('/flows');
    }
  }, [flowId, setActiveFlow, navigate]);

  useEffect(() => {
    if (isMobile) {
      setShowRightSidebar(false);
    }
  }, [isMobile]);

  useEffect(() => {
    if (isMobile && (selectedNodeId || selectedEdgeId)) {
      setIsSidebarOpen(true);
    }
  }, [isMobile, selectedNodeId, selectedEdgeId]);

  const handleToggleRightSidebar = () => {
    if (isMobile) {
      setIsSidebarOpen(true);
    } else {
      setShowRightSidebar(!showRightSidebar);
    }
  };

  const sidebarTitle = selectedNodeId
    ? 'Node Settings'
    : selectedEdgeId
      ? 'Edge Settings'
      : 'Flow Settings';

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
          showRightSidebar={isMobile ? true : showRightSidebar}
          onToggleLeftSidebar={() => {}}
          onToggleRightSidebar={handleToggleRightSidebar}
        />
        {!isMobile && showRightSidebar && (
          <RightSidebar onToggle={() => setShowRightSidebar(false)} />
        )}
      </div>

      {isMobile && (
        <>
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="fixed bottom-20 right-4 z-20 rounded-full shadow-md bg-background"
            onClick={() => setIsSidebarOpen(true)}
          >
            <Settings2 className="w-4 h-4" />
          </Button>
          <Sheet open={isSidebarOpen} onOpenChange={setIsSidebarOpen}>
            <SheetContent side="right" className="w-full sm:max-w-sm p-0 overflow-hidden flex flex-col">
              <SheetHeader className="px-4 pt-4 pb-0">
                <SheetTitle>{sidebarTitle}</SheetTitle>
              </SheetHeader>
              <div className="flex-1 min-h-0 overflow-hidden">
                <RightSidebar
                  variant="sheet"
                  onToggle={() => setIsSidebarOpen(false)}
                />
              </div>
            </SheetContent>
          </Sheet>
        </>
      )}
    </div>
  );
}
