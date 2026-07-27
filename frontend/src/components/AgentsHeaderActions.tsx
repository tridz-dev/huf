import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';
import { usePermissions } from '../contexts/PermissionsContext';

export function AgentsHeaderActions() {
  const navigate = useNavigate();
  const { hasCapability } = usePermissions();

  const handleNewAgent = () => {
    navigate('/agents/new');
  };

  if (!hasCapability('agent.create')) {
    return null;
  }

  return (
    <Button variant="display" onClick={handleNewAgent} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      New Agent
    </Button>
  );
}
