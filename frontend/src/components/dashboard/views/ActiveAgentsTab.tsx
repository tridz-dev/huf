import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap, Loader2 } from 'lucide-react';
import { getAgents } from '@/services/agentApi';
import type { AgentDoc } from '@/types/agent.types';
import { LedgerSection, LedgerRow } from '@/components/dashboard';

interface ActiveAgentsTabProps {
  agents?: AgentDoc[];
  loading?: boolean;
}

function getAgentStatus(agent: AgentDoc): { variant: 'run' | 'idle' | 'ok'; label: string } {
  if (agent.last_run) {
    const lastRun = new Date(agent.last_run);
    const now = new Date();
    const diffMs = now.getTime() - lastRun.getTime();
    if (diffMs >= 0 && diffMs < 10 * 60 * 1000) {
      return { variant: 'run', label: 'Running' };
    }
  }
  if ((agent.total_run ?? 0) > 0) {
    return { variant: 'ok', label: 'Active' };
  }
  return { variant: 'idle', label: 'Idle' };
}

export function ActiveAgentsTab({ agents: providedAgents, loading: providedLoading }: ActiveAgentsTabProps) {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentDoc[]>(providedAgents || []);
  const [loading, setLoading] = useState(providedLoading ?? true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (providedAgents !== undefined) {
      setAgents(providedAgents);
      setLoading(providedLoading ?? false);
      return;
    }

    async function fetchActiveAgents() {
      try {
        setLoading(true);
        setError(null);

        const response = await getAgents({
          status: 'active',
          limit: 10,
          page: 1,
        });

        const agentList = Array.isArray(response) ? response : response.items;
        const activeAgents = agentList.filter((agent) => agent.disabled === 0);

        setAgents(activeAgents.slice(0, 10));
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to fetch agents'));
      } finally {
        setLoading(false);
      }
    }

    fetchActiveAgents();
  }, [providedAgents, providedLoading]);

  const handleAgentClick = (agentName: string) => {
    navigate(`/agents/${agentName}`);
  };

  return (
    <LedgerSection title="Active agents">
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-steel-soft" />
        </div>
      ) : error ? (
        <div className="text-center py-8 text-signal-ink">
          <p className="font-body font-semibold">Failed to load agents</p>
          <p className="font-mono text-[12px] text-steel mt-1">{error.message}</p>
        </div>
      ) : agents.length === 0 ? (
        <div className="text-center py-8 text-steel font-body text-[14px]">
          No active agents
        </div>
      ) : (
        agents.map((agent) => {
          const status = getAgentStatus(agent);
          return (
            <LedgerRow
              key={agent.name}
              name={agent.agent_name || agent.name}
              sub={`id · ${agent.name}`}
              meta={agent.model || 'Unknown model'}
              count={
                <>
                  <Zap className="w-[13px] h-[13px] text-steel-soft" />
                  {agent.total_run || 0}
                </>
              }
              status={{ variant: status.variant, label: status.label }}
              onClick={() => handleAgentClick(agent.name)}
            />
          );
        })
      )}
    </LedgerSection>
  );
}
