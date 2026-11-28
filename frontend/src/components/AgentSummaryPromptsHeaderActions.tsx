import { useResourceAccess } from '@/hooks/permissions/useResourceAccess';
import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function AgentSummaryPromptsHeaderActions() {
  const navigate = useNavigate();

  const { canCreate } = useResourceAccess('summaryPrompt');
  const handleNewPrompt = () => {
    navigate('/summary-prompts/new');
  };

  if (!canCreate) return null;

  return (
    <Button variant="display" onClick={handleNewPrompt}>
      <Plus className="mr-2 h-4 w-4" />
      New summary prompt
    </Button>
  );
}
