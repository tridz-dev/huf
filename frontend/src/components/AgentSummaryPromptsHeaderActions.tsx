import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function AgentSummaryPromptsHeaderActions() {
  const navigate = useNavigate();

  const handleNewPrompt = () => {
    navigate('/summary-prompts/new');
  };

  return (
    <Button onClick={handleNewPrompt}>
      <Plus className="mr-2 h-4 w-4" />
      New Summary Prompt
    </Button>
  );
}
