import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { FlowCanvas } from '../components/FlowCanvas';
import { RightSidebar } from '../components/RightSidebar';
import { useFlowContext } from '../contexts/FlowContext';
import { Button } from '@/components/ui/button';
import { toast } from '@/lib/toast';
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet';
import { FlowStepsList } from '@/components/flow/phone/FlowStepsList';
import { PhoneBanner } from '@/components/flow/phone/PhoneBanner';
import { setPhoneFlowView, usePhoneFlowView } from '@/components/flow/phone/usePhoneFlowView';
import { FLOW_PANEL_ATTR } from '@/components/flow/canvas/KeepSelectedVisible';
import { StepPanelResizer } from '@/components/flow/panel/StepPanelResizer';
import { useStepPanelLayout } from '@/components/flow/panel/useStepPanelLayout';
import { useViewport } from '@/lib/ui/responsive';

export function FlowCanvasPage() {
  const { flowId } = useParams<{ flowId: string }>();
  const navigate = useNavigate();
  const { isPhone, width: windowWidth } = useViewport();
  const { setActiveFlow, activeFlow, selectedNodeId, selectedEdgeId, setSelectedNode, setSelectedEdge } = useFlowContext();
  const [showRightSidebar, setShowRightSidebar] = useState(true);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const { view: phoneView } = usePhoneFlowView();
  const layout = useStepPanelLayout(rootRef, windowWidth);
  // The panel sits beside the canvas when the canvas keeps room (520px); otherwise, and on a phone, it opens over it as a sheet.
  const sheetMode = isPhone || layout.mode === 'sheet';

  useEffect(() => {
    if (flowId) {
      setActiveFlow(flowId);
    } else {
      navigate('/flows');
    }
  }, [flowId, setActiveFlow, navigate]);

  // Each flow opens on its steps list on a phone.
  useEffect(() => setPhoneFlowView('steps'), [flowId]);

  // The window title names the flow (the tab, history and screen readers all use it).
  useEffect(() => {
    if (!activeFlow?.name) return;
    const before = document.title;
    document.title = `${activeFlow.name} - Flows - Huf AI`;
    return () => { document.title = before; };
  }, [activeFlow?.name]);

  // A toast is about the last action: the next click or key press in the editor dismisses it (toasts
  // themselves stay clickable, e.g. an Undo button).
  useEffect(() => {
    const dismiss = (event: Event) => {
      if (event.target instanceof Element && event.target.closest('[data-sonner-toaster]')) return;
      toast.dismiss();
    };
    document.addEventListener('pointerdown', dismiss, true);
    return () => document.removeEventListener('pointerdown', dismiss, true);
  }, []);

  // Opening a step (or a connection) shows its settings in the sheet when the panel is not docked.
  useEffect(() => {
    if (sheetMode && (selectedNodeId || selectedEdgeId)) setIsSidebarOpen(true);
    if (!sheetMode) setIsSidebarOpen(false);
  }, [sheetMode, selectedNodeId, selectedEdgeId]);

  const closeSheet = () => {
    setIsSidebarOpen(false);
    // Forget the selection too, so tapping the same step again opens it again.
    setSelectedNode(null);
    setSelectedEdge(null);
  };

  const handleToggleRightSidebar = () => {
    if (sheetMode) setIsSidebarOpen(true);
    else setShowRightSidebar(!showRightSidebar);
  };

  const sidebarTitle = selectedNodeId ? 'Step settings' : selectedEdgeId ? 'Connection settings' : 'Flow settings';

  if (!activeFlow) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <div className="text-center">
          <div className="font-body text-steel-soft mb-2">Loading flow...</div>
        </div>
      </div>
    );
  }

  const showSteps = isPhone && phoneView === 'steps';
  return (
    <div ref={rootRef} className="flex h-full w-full flex-col overflow-hidden" data-testid="flow-page" data-layout={isPhone ? 'phone' : layout.mode}>
      {isPhone && <PhoneBanner />}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className="flex min-w-0 flex-1 overflow-hidden">
          {showSteps ? (
            <div className="relative flex-1 overflow-hidden">
              <FlowStepsList />
              <Button type="button" variant="outline" className="absolute bottom-4 right-4 min-h-11 bg-panel shadow-sm" data-testid="flow-phone-show-map" onClick={() => setPhoneFlowView('map')}>
                Show map
              </Button>
            </div>
          ) : (
            <FlowCanvas
              showLeftSidebar={true}
              showRightSidebar={isPhone ? true : sheetMode ? false : showRightSidebar}
              onToggleLeftSidebar={() => {}}
              onToggleRightSidebar={handleToggleRightSidebar}
            />
          )}
          {!sheetMode && showRightSidebar && (
            <div ref={layout.panelRef} className="relative shrink-0 [&>[data-testid=flow-config-sidebar]]:!w-full" data-testid="flow-step-panel" data-width={layout.panelWidth}>
              <StepPanelResizer width={layout.panelWidth} onResize={layout.resize} onResizeEnd={layout.commit} />
              <RightSidebar onToggle={() => setShowRightSidebar(false)} />
            </div>
          )}
        </div>
      </div>

      {sheetMode && (
        <Sheet open={isSidebarOpen} onOpenChange={(open) => (open ? setIsSidebarOpen(true) : closeSheet())}>
          <SheetContent
            side="right"
            {...{ [FLOW_PANEL_ATTR]: '' }}
            className="flex w-full flex-col gap-0 overflow-hidden p-0 max-w-none sm:w-[min(420px,62vw)] sm:max-w-none [&>button]:hidden"
            data-testid="flow-step-sheet"
          >
            <div className="flex shrink-0 items-center gap-2 border-b border-line px-2 py-1.5">
              <Button type="button" variant="ghost" size="sm" className="min-h-11 gap-1.5 px-2" data-testid="flow-sheet-back" onClick={closeSheet}>
                <ArrowLeft className="h-4 w-4" aria-hidden />
                Back to the flow
              </Button>
              <SheetTitle className="ml-auto truncate pr-2 text-sm font-medium">{sidebarTitle}</SheetTitle>
              <SheetDescription className="sr-only">The settings of the step you picked.</SheetDescription>
            </div>
            {isPhone && (
              <p className="shrink-0 border-b border-line bg-paper-deep px-4 py-2 text-xs text-steel" data-testid="flow-phone-read-only-note">
                Editing steps works best on a larger screen. Here you can read how this step is set up.
              </p>
            )}
            <div className="min-h-0 flex-1 overflow-hidden">
              {/* On a phone the step forms are for reading: every field is switched off. */}
              <fieldset disabled={isPhone} className="contents [&_input:disabled]:!opacity-100 [&_input:disabled]:text-ink [&_textarea:disabled]:!opacity-100 [&_textarea:disabled]:text-ink [&_[role=combobox]:disabled]:!opacity-100 [&_[role=combobox]:disabled]:text-ink">
                <RightSidebar variant="sheet" onToggle={closeSheet} />
              </fieldset>
            </div>
          </SheetContent>
        </Sheet>
      )}
    </div>
  );
}
