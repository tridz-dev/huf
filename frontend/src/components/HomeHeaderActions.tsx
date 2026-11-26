import { PermissionsContext } from '@/contexts/PermissionsContext';
import { useContext } from 'react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Plus, SquareAsterisk, Workflow } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function HomeHeaderActions() {
  const navigate = useNavigate();

  const permissions = useContext(PermissionsContext);
  const can = (capability: string) => !permissions || (!permissions.isLoading && permissions.hasCapability(capability));
  const canOpenFlows = can('flows.use');
  const canOpenAgents = can('agent.use');

  const handleNewFlow = () => {
    navigate('/flows');
  };

  const handleNewAgent = () => {
    navigate('/agents');
  };

  if (!canOpenFlows && !canOpenAgents) return null;

  return (
    <div className="flex items-center gap-2">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="display" size="sm">
            <Plus className="w-4 h-4 mr-2" />
            New
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {canOpenFlows && (
          <DropdownMenuItem onClick={handleNewFlow}>
            <Workflow className="w-4 h-4 mr-2" />
            Open flows
          </DropdownMenuItem>
          )}
          {canOpenAgents && (
          <DropdownMenuItem onClick={handleNewAgent}>
            <SquareAsterisk className="w-4 h-4 mr-2" />
            Open agents
          </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
