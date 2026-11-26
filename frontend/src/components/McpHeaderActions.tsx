import { useResourceAccess } from '@/hooks/permissions/useResourceAccess';
import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';

export function McpHeaderActions() {
  const navigate = useNavigate();
  const { canCreate } = useResourceAccess('mcp');

  const handleNewMcp = () => {
    navigate('/mcp/new');
  };

  if (!canCreate) {
    return null;
  }

  return (
    <Button variant="display" onClick={handleNewMcp} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      New MCP server
    </Button>
  );
}

