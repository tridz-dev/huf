import { Plus } from 'lucide-react';
import { Button } from './ui/button';
import { useIntegrations } from '../contexts/IntegrationsContext';

export function IntegrationsHeaderActions() {
  const { onAddProvider } = useIntegrations();

  return (
    <Button onClick={onAddProvider} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      Add Provider
    </Button>
  );
}
