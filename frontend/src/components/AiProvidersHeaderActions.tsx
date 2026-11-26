import { useResourceAccess } from '@/hooks/permissions/useResourceAccess';
import { Plus } from 'lucide-react';
import { Button } from './ui/button';
import { useAiProviders } from '../contexts/AiProvidersContext';

export function AiProvidersHeaderActions() {
  const { onAddProvider } = useAiProviders();
  const { canCreate } = useResourceAccess('provider');

  if (!canCreate) return null;

  return (
    <Button variant="display" onClick={onAddProvider} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      Add provider
    </Button>
  );
}
