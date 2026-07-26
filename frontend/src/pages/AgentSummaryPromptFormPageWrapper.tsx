import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { AgentSummaryPromptFormPage } from './AgentSummaryPromptFormPage';
import { getAgentSummaryPrompt } from '../services/agentSummaryPromptApi';

export { AgentSummaryPromptFormPageWrapper };
export default AgentSummaryPromptFormPageWrapper;

function AgentSummaryPromptFormPageWrapper() {
  const { id } = useParams<{ id: string }>();
  const isNew = id === 'new';
  const [promptTitle, setPromptTitle] = useState<string>('New Agent Summary Prompt');

  useEffect(() => {
    if (isNew) {
      setPromptTitle('New Agent Summary Prompt');
      return;
    }

    if (!id) return;
    getAgentSummaryPrompt(id)
      .then((doc) => {
        setPromptTitle(doc.title || id);
      })
      .catch(() => {
        setPromptTitle(id);
      });
  }, [id, isNew]);

  const breadcrumbs = [
    { label: 'Agent Summary Prompts', href: '/summary-prompts' },
    { label: promptTitle },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <AgentSummaryPromptFormPage />
    </UnifiedLayout>
  );
}
