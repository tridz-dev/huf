import { useEffect, useMemo, useState } from 'react';
import { getAgents, getDocTypes } from '@/services/agentApi';
import type { AgentDoc } from '@/types/agent.types';

export function useToolCreationOptions() {
  const [docTypes, setDocTypes] = useState<Array<{ name: string }>>([]);
  const [agents, setAgents] = useState<AgentDoc[]>([]);
  const [loadingData, setLoadingData] = useState(false);

  useEffect(() => {
    const loadData = async () => {
      setLoadingData(true);
      try {
        const [doctypes, agentsList] = await Promise.all([getDocTypes(), getAgents()]);
        setDocTypes(doctypes || []);
        setAgents(Array.isArray(agentsList) ? agentsList : (agentsList as any)?.items || []);
      } catch (error) {
        console.error('Error loading tool form options:', error);
      } finally {
        setLoadingData(false);
      }
    };

    loadData();
  }, []);

  const docTypeOptions = useMemo(
    () => docTypes.map((dt) => ({ value: dt.name, label: dt.name })),
    [docTypes]
  );

  const agentOptions = useMemo(
    () =>
      agents.map((agent) => ({
        value: agent.name,
        label: agent.model
          ? `${agent.agent_name || agent.name} · ${agent.model}`
          : agent.agent_name || agent.name,
      })),
    [agents]
  );

  return {
    loadingData,
    docTypeOptions,
    agentOptions,
  };
}
