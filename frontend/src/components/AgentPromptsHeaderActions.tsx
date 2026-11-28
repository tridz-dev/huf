import { useResourceAccess } from '@/hooks/permissions/useResourceAccess';
import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';

export function AgentPromptsHeaderActions() {
  const navigate = useNavigate();

  const { canCreate } = useResourceAccess('prompt');
  const handleNewPrompt = () => {
    navigate('/prompts/new');
  };

  if (!canCreate) return null;

  return (
    <Button variant="display" onClick={handleNewPrompt} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      New agent prompt
    </Button>
  );
}
