import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { AgentPromptFormPage } from './AgentPromptFormPage';
import { getAgentPrompt } from '../services/agentPromptApi';

export { AgentPromptFormPageWrapper };
export default AgentPromptFormPageWrapper;

function AgentPromptFormPageWrapper() {
  const { id } = useParams<{ id: string }>();
  const [promptTitle, setPromptTitle] = useState<string>('New Agent Prompt');
  const isNew = id === 'new';

  useEffect(() => {
    if (id && !isNew) {
      getAgentPrompt(id)
        .then((prompt) => {
          setPromptTitle(prompt.title || prompt.name);
        })
        .catch((error) => {
          console.error('Error loading Agent Prompt:', error);
          setPromptTitle('Agent Prompt');
        });
    } else {
      setPromptTitle('New Agent Prompt');
    }
  }, [id, isNew]);

  const breadcrumbs = [{ label: 'Agent Prompts', href: '/prompts' }, { label: promptTitle }];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <AgentPromptFormPage />
    </UnifiedLayout>
  );
}
