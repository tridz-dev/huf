import { Plus } from 'lucide-react';
import { Button } from './ui/button';
import { useAiProviders } from '../contexts/AiProvidersContext';

export function AiProvidersHeaderActions() {
  const { onAddProvider } = useAiProviders();

  return (
    <Button onClick={onAddProvider} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      Add Provider
    </Button>
  );
}
