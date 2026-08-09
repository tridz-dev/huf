import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Plus, Bot, Workflow } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function HomeHeaderActions() {
  const navigate = useNavigate();

  const handleNewFlow = () => {
    navigate('/flows');
  };

  const handleNewAgent = () => {
    navigate('/agents');
  };

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
          <DropdownMenuItem onClick={handleNewFlow}>
            <Workflow className="w-4 h-4 mr-2" />
            Open flows
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleNewAgent}>
            <Bot className="w-4 h-4 mr-2" />
            Open agents
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
