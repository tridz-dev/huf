import { Plus } from 'lucide-react';
import { Button } from './ui/button';
import { useModels } from '../contexts/ModelsContext';

export function ModelsHeaderActions() {
  const { onAddModel } = useModels();

  return (
    <Button onClick={onAddModel} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      Add Model
    </Button>
  );
}
