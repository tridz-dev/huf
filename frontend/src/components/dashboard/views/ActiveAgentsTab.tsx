import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { getAgents } from '@/services/agentApi';
import type { AgentDoc } from '@/types/agent.types';
import { Loader2, Zap } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

interface ActiveAgentsTabProps {
  agents?: AgentDoc[];
  loading?: boolean;
}

export function ActiveAgentsTab({ agents: providedAgents, loading: providedLoading }: ActiveAgentsTabProps) {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentDoc[]>(providedAgents || []);
  const [loading, setLoading] = useState(providedLoading ?? true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    // If agents are provided, use them and skip fetching
    if (providedAgents !== undefined) {
      setAgents(providedAgents);
      setLoading(providedLoading ?? false);
      return;
    }

    // Otherwise, fetch agents
    async function fetchActiveAgents() {
      try {
        setLoading(true);
        setError(null);
        
        const response = await getAgents({
          status: 'active',
          limit: 10,
          page: 1,
        });

        // Handle both paginated and array responses
        const agentList = Array.isArray(response) ? response : response.items;
        
        // Filter to ensure only active agents (disabled = 0)
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
    <Card>
      <CardHeader>
        <CardTitle>Active Agents</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="text-center py-8 text-destructive">
            <p>Failed to load agents</p>
            <p className="text-sm text-muted-foreground mt-1">{error.message}</p>
          </div>
        ) : agents.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No active agents
          </div>
        ) : (
          <div className="space-y-3">
            {agents.map((agent) => (
              <div
                key={agent.name}
                className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors cursor-pointer"
                onClick={() => handleAgentClick(agent.name)}
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  {agent.agent_color && (
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0 border border-border"
                      style={{ backgroundColor: agent.agent_color }}
                      aria-hidden
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate flex items-center gap-2">
                      {agent.agent_name || agent.name}
                      {agent.allow_chat === 1 && (
                        <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                          Chat
                        </Badge>
                      )}
                    </div>
                    <div className="text-sm text-muted-foreground flex items-center gap-2 mt-1">
                      <span>{agent.provider || 'Unknown provider'}</span>
                      <span>•</span>
                      <span>{agent.model || 'Unknown model'}</span>
                      <span>•</span>
                      <span className="flex items-center gap-1">
                        <Zap className="w-4 h-4" />
                        {agent.total_run || 0}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

