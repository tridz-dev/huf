import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';
import { usePermissions } from '../contexts/PermissionsContext';

export function McpHeaderActions() {
  const navigate = useNavigate();
  const { hasCapability } = usePermissions();

  const handleNewMcp = () => {
    navigate('/mcp/new');
  };

  if (!hasCapability('system.mcp.manage')) {
    return null;
  }

  return (
    <Button variant="display" onClick={handleNewMcp} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      New MCP Server
    </Button>
  );
}

