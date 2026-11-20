import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { getAgents, linkKnowledgeToAgent } from '@/services/agentApi';
import { getAgentsForSource } from '@/services/knowledge/usageApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { AgentDoc } from '@/types/agent.types';

interface ConnectAgentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  knowledgeSource: string;
  /** Called after agents were connected, so "Used by N agents" can refresh. */
  onConnected: () => void;
}

/** Pick agents to attach this knowledge source to. */
export function ConnectAgentDialog({ open, onOpenChange, knowledgeSource, onConnected }: ConnectAgentDialogProps) {
  const [agents, setAgents] = useState<AgentDoc[] | null>(null);
  const [linked, setLinked] = useState<Set<string>>(new Set());
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setPicked(new Set());
    setError(null);
    setAgents(null);
    Promise.all([getAgents(), getAgentsForSource(knowledgeSource)])
      .then(([list, used]) => {
        setAgents(Array.isArray(list) ? list : list.items);
        setLinked(new Set(used));
      })
      .catch((e) => setError(getFrappeErrorMessage(e) || 'Could not load agents'));
  }, [open, knowledgeSource]);

  const toggle = (name: string) =>
    setPicked((cur) => {
      const next = new Set(cur);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const save = async () => {
    setBusy(true);
    const failed: string[] = [];
    for (const name of picked) {
      try {
        await linkKnowledgeToAgent(name, knowledgeSource);
      } catch {
        failed.push(name);
      }
    }
    setBusy(false);
    const ok = picked.size - failed.length;
    if (ok > 0) toast.success(`Connected to ${ok} ${ok === 1 ? 'agent' : 'agents'}.`);
    if (failed.length > 0) toast.error(`Could not connect: ${failed.join(', ')}`);
    onConnected();
    if (failed.length === 0) onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(o) => (busy ? undefined : onOpenChange(o))}>
      <DialogScrollContent className="max-w-lg">
        <DialogScrollHeader>
          <DialogTitle>Connect to an agent</DialogTitle>
          <DialogDescription>Choose the agents that should answer from this knowledge source.</DialogDescription>
        </DialogScrollHeader>
        <DialogScrollBody className="space-y-2 py-2">
          {error && <p className="text-sm text-destructive">{error}</p>}
          {!agents && !error && (
            <div className="flex justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-steel-soft" />
            </div>
          )}
          {agents && agents.length === 0 && <p className="text-sm text-steel">No agents yet. Create an agent first.</p>}
          {agents?.map((a) => {
            const isLinked = linked.has(a.name);
            const locked = a.is_system === 1;
            const reason = isLinked ? 'Already connected' : locked ? 'System agents cannot be edited' : '';
            return (
              <label
                key={a.name}
                className={`flex items-start gap-3 rounded-md border p-3 ${reason ? 'opacity-70' : 'cursor-pointer hover:bg-muted'}`}
              >
                <Checkbox
                  checked={isLinked || picked.has(a.name)}
                  disabled={!!reason || busy}
                  onCheckedChange={() => toggle(a.name)}
                  className="mt-0.5"
                />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{a.agent_name || a.name}</span>
                  {a.description && <span className="block truncate text-xs text-steel">{a.description}</span>}
                  {reason && <span className="block text-xs text-steel-soft">{reason}</span>}
                </span>
              </label>
            );
          })}
        </DialogScrollBody>
        <DialogScrollFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button type="button" onClick={() => void save()} disabled={busy || picked.size === 0}>
            {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {picked.size > 0 ? `Connect ${picked.size} ${picked.size === 1 ? 'agent' : 'agents'}` : 'Connect'}
          </Button>
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
