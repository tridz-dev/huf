import { Plus } from 'lucide-react';

import { useModels } from '@/contexts/ModelsContext';

import { Button } from './ui/button';

export function ModelsHeaderActions() {
  const { onAddModel } = useModels();

  return (
    <Button onClick={onAddModel} size="sm">
      <Plus className="mr-2 h-4 w-4" />
      Add Model
    </Button>
  );
}
