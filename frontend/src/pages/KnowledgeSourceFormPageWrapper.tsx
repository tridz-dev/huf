import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { KnowledgeSourceFormPage } from './KnowledgeSourceFormPage';
import { getKnowledgeSource } from '../services/knowledgeApi';
import { getAgent } from '../services/agentApi';

export { KnowledgeSourceFormPageWrapper };
export default KnowledgeSourceFormPageWrapper;

function KnowledgeSourceFormPageWrapper() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const fromAgent = searchParams.get('agent');
  const [sourceName, setSourceName] = useState<string>('New Knowledge Source');
  const [agentLabel, setAgentLabel] = useState<string>('Agent');
  const isNew = id === 'new';

  useEffect(() => {
    if (fromAgent) {
      getAgent(fromAgent)
        .then((agent) => {
          setAgentLabel(agent.agent_name || agent.name);
        })
        .catch(() => {
          setAgentLabel('Agent');
        });
    }
  }, [fromAgent]);

  useEffect(() => {
    if (id && !isNew) {
      getKnowledgeSource(id)
        .then((source) => {
          setSourceName(source.source_name || source.name);
        })
        .catch((error) => {
          console.error('Error loading knowledge source:', error);
          setSourceName('Knowledge Source');
        });
    } else {
      setSourceName('New Knowledge Source');
    }
  }, [id, isNew]);

  const breadcrumbs = [
    ...(fromAgent
      ? [{ label: agentLabel, href: `/agents/${fromAgent}#knowledge` }]
      : []),
    { label: 'Knowledge', href: '/knowledge' },
    { label: sourceName },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <KnowledgeSourceFormPage />
    </UnifiedLayout>
  );
}
