/**
 * DeleteAgentFlow: ConfirmDestructive driven by get_agent_delete_precheck.
 * Honest dependents; Disable instead / Archive when linked; Delete only when allowed.
 */
import { useEffect, useState } from 'react';
import { ConfirmDestructive, type Dependent } from '@/components/grid';
import { AttentionBanner } from '@/components/patterns';
import { archiveAgent, deleteAgentCascade, getAgentDeletePrecheck, type DeletePrecheck } from '@/services/agentForm/agentFormApi';

export interface DeleteAgentFlowProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentName: string;
  onDone: (result: 'deleted' | 'archived') => void;
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export function DeleteAgentFlow({ open, onOpenChange, agentName, onDone }: DeleteAgentFlowProps) {
  const [pre, setPre] = useState<DeletePrecheck | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setPre(null); setFailed(false);
    getAgentDeletePrecheck(agentName).then((p) => live && setPre(p)).catch(() => live && setFailed(true));
    return () => { live = false; };
  }, [open, agentName]);

  if (open && failed) {
    return <AttentionBanner message="Could not check what depends on this agent. Try again." action={{ label: 'Close', onClick: () => onOpenChange(false) }} />;
  }
  if (!pre) return null;

  const c = pre.counts;
  // Automations are triggers under the hood; do not double count.
  const automations = Math.max(c.automations, c.triggers);
  const dependents: Dependent[] = [
    c.conversations > 0 && { kind: 'Chats', label: plural(c.conversations, 'conversation', 'conversations') },
    c.runs > 0 && { kind: 'Runs', label: plural(c.runs, 'run', 'runs') },
    automations > 0 && { kind: 'Automations', label: plural(automations, 'automation', 'automations'), detail: 'will stop running' },
  ].filter(Boolean) as Dependent[];

  if (!pre.can_delete && !pre.can_archive) {
    return <AttentionBanner message="You do not have permission to delete or disable this agent." action={{ label: 'Close', onClick: () => onOpenChange(false) }} />;
  }

  const archive = async () => { await archiveAgent(agentName); onDone('archived'); onOpenChange(false); };
  const canDelete = pre.can_delete;
  const linkedNeedsArchive = pre.has_linked && pre.can_archive;

  return (
    <ConfirmDestructive open={open} onOpenChange={onOpenChange}
      title={canDelete ? `Delete "${agentName}"?` : `Disable "${agentName}"?`}
      consequence={canDelete
        ? (pre.has_linked ? 'Deleting removes this agent and its history for good.' : 'Deleting removes this agent and its settings for good.')
        : 'You do not have permission to delete agents, but you can disable it. Its history is kept.'}
      dependents={dependents}
      recovery={canDelete ? "This can't be undone." : 'You can turn it back on any time.'}
      confirmText={canDelete ? agentName : undefined}
      actionLabel={canDelete ? 'Delete' : 'Disable'}
      onConfirm={async () => {
        if (canDelete) { await deleteAgentCascade(agentName); onDone('deleted'); } else { await archive(); }
      }}
      alternative={canDelete && linkedNeedsArchive && !pre.disabled ? { label: 'Disable instead', onClick: () => void archive() } : undefined} />
  );
}
