import { useEffect, useMemo, useState } from 'react';
import { Bot, Loader2, Search } from 'lucide-react';
import { toast } from 'sonner';
import { Dialog, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import {
  DialogScrollBody,
  DialogScrollContent,
  DialogScrollFooter,
  DialogScrollHeader,
} from '@/components/ui/dialog-scroll';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { getAgents } from '@/services/agentApi';
import {
  connectAgentToChannel,
  getChannelAgentConnection,
  type ChannelAgentConnection,
} from '@/services/gatewayApi';
import type { AgentDoc } from '@/types/agent.types';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { cn } from '@/lib/utils';

interface ConnectChannelAgentModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The channel credential (Integration Settings name). */
  integrationName: string;
  /** Called after an agent was connected, so the page can reload its gateway. */
  onConnected?: () => void;
}

/** Pick the agent that answers messages on a messaging channel (WhatsApp, Telegram, ...). */
export function ConnectChannelAgentModal({
  open,
  onOpenChange,
  integrationName,
  onConnected,
}: ConnectChannelAgentModalProps) {
  const [agents, setAgents] = useState<AgentDoc[]>([]);
  const [connection, setConnection] = useState<ChannelAgentConnection | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const gateway = connection?.gateways[0];
  const currentAgent = gateway?.default_target_type === 'Agent' ? gateway.default_agent || '' : '';

  useEffect(() => {
    if (!open) {
      setSearch('');
      setSelected('');
      return;
    }
    setLoading(true);
    Promise.all([getAgents(), getChannelAgentConnection(integrationName)])
      .then(([result, conn]) => {
        setAgents((Array.isArray(result) ? result : result.items) || []);
        setConnection(conn);
        const first = conn.gateways[0];
        if (first?.default_target_type === 'Agent' && first.default_agent) setSelected(first.default_agent);
      })
      .catch((error) => toast.error(getFrappeErrorMessage(error) || 'Failed to load agents'))
      .finally(() => setLoading(false));
  }, [open, integrationName]);

  const agentLabel = (name: string) => agents.find((a) => a.name === name)?.agent_name || name;

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return agents;
    return agents.filter(
      (a) => (a.agent_name || '').toLowerCase().includes(query) || a.name.toLowerCase().includes(query),
    );
  }, [agents, search]);

  const handleConnect = async () => {
    if (!selected) return;
    setSubmitting(true);
    try {
      const result = await connectAgentToChannel({
        integrationSettings: integrationName,
        agent: selected,
        gatewayName: gateway?.name,
      });
      const name = agentLabel(selected);
      toast.success(
        result.previous_agent
          ? `${name} now answers this channel instead of ${agentLabel(result.previous_agent)}`
          : `${name} now answers this channel`,
      );
      if (!result.enabled) {
        toast.warning('The channel is still off', {
          description: result.enable_error || 'Finish its setup on the Channel tab, then turn it on.',
        });
      }
      onConnected?.();
      onOpenChange(false);
    } catch (error) {
      toast.error(getFrappeErrorMessage(error) || 'Failed to connect the agent');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogScrollContent className="sm:max-w-lg">
        <DialogScrollHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bot className="h-5 w-5" />
            Use in agent
          </DialogTitle>
          <DialogDescription>
            Choose the agent that answers messages on this channel. It also gets the channel&apos;s tools.
          </DialogDescription>
        </DialogScrollHeader>

        <DialogScrollBody className="space-y-3 py-2">
          {!loading && (
            <p className="text-xs text-steel">
              {currentAgent ? (
                <>
                  Currently answered by <span className="font-medium text-ink">{agentLabel(currentAgent)}</span>.
                </>
              ) : gateway ? (
                'No agent answers this channel yet.'
              ) : (
                'This channel has no gateway yet. One is created for you, with new senders needing approval.'
              )}
            </p>
          )}

          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-steel-soft" />
            <Input
              placeholder="Search agents..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>

          {loading ? (
            <div className="flex items-center gap-2 py-4 text-sm text-steel-soft">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading agents...
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-4 text-center text-sm text-steel-soft">No agents found.</div>
          ) : (
            <RadioGroup
              value={selected}
              onValueChange={setSelected}
              className="gap-0 divide-y divide-border rounded-md border border-border"
            >
              {filtered.map((agent) => (
                <Label
                  key={agent.name}
                  className={cn(
                    'flex cursor-pointer items-start gap-3 p-3 font-normal leading-normal transition-colors hover:bg-muted/50',
                    selected === agent.name && 'bg-muted/50',
                  )}
                >
                  <RadioGroupItem value={agent.name} className="mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{agent.agent_name || agent.name}</div>
                    {agent.description && (
                      <div className="truncate text-xs text-steel-soft">{agent.description}</div>
                    )}
                  </div>
                  {agent.name === currentAgent && <span className="text-xs text-steel">Current</span>}
                </Label>
              ))}
            </RadioGroup>
          )}
        </DialogScrollBody>

        <DialogScrollFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleConnect} disabled={!selected || selected === currentAgent || submitting}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Use in agent
          </Button>
        </DialogScrollFooter>
      </DialogScrollContent>
    </Dialog>
  );
}
