import { useState } from 'react';
import { Workflow } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ProposeProcedureDialog } from '@/components/ProposeProcedureDialog';

interface ProposeProcedureActionProps {
  agentRunName: string;
}

/**
 * "Save these steps as a procedure" action for a completed assistant turn that involved at
 * least one tool call (see ChatMessage.tsx, which only renders this when
 * `message.tools` is non-empty). Opens ProposeProcedureDialog, which does the
 * actual propose-then-accept round trip against huf.ai.procedure_proposal.
 */
export function ProposeProcedureAction({ agentRunName }: ProposeProcedureActionProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="text-steel-soft hover:text-ink"
        onClick={() => setOpen(true)}
        aria-label="Save these steps as a procedure"
        title="Save these steps as a procedure"
      >
        <Workflow className="size-[15px]" />
      </Button>
      {open && (
        <ProposeProcedureDialog agentRunName={agentRunName} open={open} onOpenChange={setOpen} />
      )}
    </>
  );
}
