import { useState } from 'react';
import { Workflow } from 'lucide-react';
import { ProposeProcedureDialog } from '@/components/ProposeProcedureDialog';

interface ProposeProcedureActionProps {
  agentRunName: string;
}

/**
 * "Save these steps as a procedure" suggestion for a completed assistant turn that
 * involved at least one tool call (see ChatMessage.tsx, which only renders this when
 * `message.tools` is non-empty). Opens ProposeProcedureDialog, which does the actual
 * propose-then-accept round trip against huf.ai.procedure_proposal.
 *
 * Deliberately NOT hover-gated like the copy/thumbs/retry row: this points at a feature
 * most users don't know exists yet, so it stays visible with its own label rather than
 * hiding behind hover as a bare icon (which read as a stray, unexplained control).
 */
export function ProposeProcedureAction({ agentRunName }: ProposeProcedureActionProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[11.5px] text-steel-soft transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
      >
        <Workflow className="size-[13px]" />
        Save as procedure
      </button>
      {open && (
        <ProposeProcedureDialog agentRunName={agentRunName} open={open} onOpenChange={setOpen} />
      )}
    </>
  );
}
