import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { AgentFormPage } from './AgentFormPage';
import { getAgent } from '../services/agentApi';

export function AgentFormPageWrapper() {
  const { id } = useParams<{ id: string }>();
  const [agentName, setAgentName] = useState<string>('Loading...');

  useEffect(() => {
    if (id) {
      getAgent(id).then((agent) => {
        setAgentName(agent.agent_name || agent.name);
      }).catch((error) => {
        console.error('Error loading agent:', error);
        setAgentName('Agent');
      });
    }
  }, [id]);

  const breadcrumbs = [
    { label: 'Agents', href: '/agents' },
    { label: agentName },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <AgentFormPage />
    </UnifiedLayout>
  );
}
