import { Plus } from 'lucide-react';
import { Button } from './ui/button';

export function DataHeaderActions() {
  return (
    <Button>
      <Plus className="w-4 h-4 mr-2" />
      Add Data Source
    </Button>
  );
}
