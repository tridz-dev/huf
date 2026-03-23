import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';

export function AgentPromptsHeaderActions() {
  const navigate = useNavigate();

  const handleNewPrompt = () => {
    navigate('/prompts/new');
  };

  return (
    <Button onClick={handleNewPrompt} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      New Agent Prompt
    </Button>
  );
}
