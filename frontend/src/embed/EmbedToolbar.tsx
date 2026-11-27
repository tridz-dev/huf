import { useState } from 'react';
import { CheckCircle2, Circle, History, Inbox, Loader2, Play, Save, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useFlowContext } from '@/contexts/FlowContext';
import { FlowRunHistory } from '@/components/FlowRunHistory';
import { FlowRunViewer } from '@/components/FlowRunViewer';
import { FlowMembersPanel } from '@/components/flow/members/FlowMembersPanel';
import { RunFlowDialog } from '@/components/flow/RunFlowDialog';
import { useFlowHeaderActions } from '@/components/flow/header/useFlowHeaderActions';
import { useFlowCommand } from '@/components/flow/shortcuts/flowCommands';
import { useRunParam } from '@/hooks/flow/useRunParam';
import { toast } from '@/lib/toast';
import type { EmbedPolicy } from './bridge';
import { EmbedApprovalsDrawer } from './EmbedApprovalsDrawer';

export const EMBED_TEST_LABEL = 'Test (no messages sent)';

/**
 * The toolbar of an app-owned flow in the frame: Save, a dry-run Test and this flow's Runs, approvals and People.
 * Publishing and the flow settings belong to the host, so there is no control (button, menu or shortcut) for them.
 */
export function EmbedToolbar({ policy }: { policy: EmbedPolicy }) {
  const { activeFlow, saveState, hasUnsavedChanges } = useFlowContext();
  const header = useFlowHeaderActions();
  const [panel, setPanel] = useState<'runs' | 'approvals' | 'people' | null>(null);
  const [selectedRunId, setSelectedRunId] = useRunParam();
  const flowId = activeFlow?.id;

  useFlowCommand('save', () => (hasUnsavedChanges ? void header.handleSaveDraft() : toast('Everything is saved', { id: 'flow-save-toast', duration: 2000 })), policy.can_edit);
  useFlowCommand('run', () => void header.handleRun(), policy.can_test);
  useFlowCommand('runs', () => setPanel('runs'));

  const openRun = (runId: string) => {
    setPanel(null);
    setSelectedRunId(runId);
  };

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="embed-toolbar">
      {policy.can_edit ? (
        <span className="mr-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground" data-testid="flow-save-state">
          {saveState === 'saving' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : hasUnsavedChanges ? <Circle className="h-3.5 w-3.5 fill-signal text-signal" /> : <CheckCircle2 className="h-3.5 w-3.5 text-good" />}
          {saveState === 'saving' ? 'Saving...' : saveState === 'error' ? 'Save Failed' : hasUnsavedChanges ? 'Unsaved' : 'Saved'}
        </span>
      ) : (
        <span className="mr-1 text-xs font-medium text-muted-foreground" data-testid="embed-view-only">View only</span>
      )}
      {policy.can_edit && (
        <Button variant="outline" size="sm" className="gap-2" data-testid="flow-save" onClick={header.handleSaveDraft} disabled={!activeFlow || saveState === 'saving' || !hasUnsavedChanges}>
          <Save className="h-4 w-4" /> Save
        </Button>
      )}
      {policy.can_test && (
        <Button variant="outline" size="sm" className="gap-2" data-testid="flow-run" onClick={() => void header.handleRun()} disabled={!activeFlow}>
          <Play className="h-4 w-4" /> {EMBED_TEST_LABEL}
        </Button>
      )}
      <Button variant="outline" size="sm" className="gap-2" data-testid="flow-runs" onClick={() => setPanel('runs')} disabled={!activeFlow}>
        <History className="h-4 w-4" /> Runs
      </Button>
      {policy.can_approve && (
        <Button variant="outline" size="sm" className="gap-2" data-testid="embed-approvals-open" onClick={() => setPanel('approvals')} disabled={!activeFlow}>
          <Inbox className="h-4 w-4" /> Waiting for approval
        </Button>
      )}
      <Button variant="outline" size="sm" className="gap-2" data-testid="flow-members-open" onClick={() => setPanel('people')} disabled={!activeFlow}>
        <Users className="h-4 w-4" /> People
      </Button>

      {flowId && (
        <>
          <FlowRunHistory
            flowId={flowId}
            open={panel === 'runs'}
            onOpenChange={(open) => setPanel(open ? 'runs' : null)}
            onSelectRun={setSelectedRunId}
            onRunTest={() => { setPanel(null); void header.handleRun(); }}
          />
          <FlowMembersPanel
            flowId={flowId}
            open={panel === 'people'}
            onOpenChange={(open) => setPanel(open ? 'people' : null)}
            stepName={(id) => activeFlow?.nodes.find((n) => n.id === id)?.data.label}
          />
          {policy.can_approve && (
            <EmbedApprovalsDrawer flowId={flowId} open={panel === 'approvals'} onOpenChange={(open) => setPanel(open ? 'approvals' : null)} onOpenRun={openRun} />
          )}
        </>
      )}
      <FlowRunViewer runId={selectedRunId} onClose={() => setSelectedRunId(null)} onBack={flowId ? () => { setSelectedRunId(null); setPanel('runs'); } : undefined} />
      {policy.can_test && (
        <RunFlowDialog
          open={header.showRunDialog}
          flowId={flowId ?? null}
          flowName={activeFlow?.name}
          onOpenChange={header.setShowRunDialog}
          // Always a dry run here; the server forces it too.
          onRun={(payload) => header.startRun(payload, 'test')}
          testOnly
        />
      )}
    </div>
  );
}
