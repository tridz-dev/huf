import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';

export function AgentsHeaderActions() {
  const navigate = useNavigate();

  const handleNewAgent = () => {
    navigate('/agents/new');
  };

  return (
    <Button variant="display" onClick={handleNewAgent} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      New Agent
    </Button>
  );
}
