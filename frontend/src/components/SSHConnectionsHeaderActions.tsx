import { useResourceAccess } from '@/hooks/permissions/useResourceAccess';
import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function SSHConnectionsHeaderActions() {
  const navigate = useNavigate();

  const { canCreate } = useResourceAccess('sshConnection');
  const handleNewConnection = () => {
    navigate('/ssh-connections/new');
  };

  if (!canCreate) return null;

  return (
    <Button variant="display" onClick={handleNewConnection}>
      <Plus className="mr-2 h-4 w-4" />
      New SSH connection
    </Button>
  );
}
