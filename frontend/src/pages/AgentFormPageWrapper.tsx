import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { AgentFormPage } from './AgentFormPage';
import { mockApi } from '../services/mockApi';

export function AgentFormPageWrapper() {
  const { id } = useParams<{ id: string }>();
  const [agentName, setAgentName] = useState<string>('Loading...');

  useEffect(() => {
    if (id) {
      mockApi.agents.get(id).then((agent) => {
        if (agent) {
          setAgentName(agent.agent_name);
        }
      });
    }
  }, [id]);

  const breadcrumbs = [
    { label: 'Agents', href: '/huf/agents' },
    { label: agentName },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <AgentFormPage />
    </UnifiedLayout>
  );
}
