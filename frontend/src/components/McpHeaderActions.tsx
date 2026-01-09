import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';

export function McpHeaderActions() {
  const navigate = useNavigate();

  const handleNewMcp = () => {
    navigate('/mcp/new');
  };

  return (
    <Button onClick={handleNewMcp} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      New MCP Server
    </Button>
  );
}

