import { useResourceAccess } from '@/hooks/permissions/useResourceAccess';
import { Plus } from 'lucide-react';
import { Button } from './ui/button';
import { useModels } from '../contexts/ModelsContext';

export function ModelsHeaderActions() {
  const { onAddModel } = useModels();
  const { canCreate } = useResourceAccess('model');

  if (!canCreate) return null;

  return (
    <Button variant="display" onClick={onAddModel} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      Add model
    </Button>
  );
}
