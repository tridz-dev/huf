import { Plus } from 'lucide-react';
import { Button } from './ui/button';

export function AgentsHeaderActions() {
  return (
    <Button>
      <Plus className="w-4 h-4 mr-2" />
      New Agent
    </Button>
  );
}
