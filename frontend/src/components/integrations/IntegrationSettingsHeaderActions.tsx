import { Plus } from 'lucide-react';
import { Button } from '../ui/button';
import { useIntegrationSettingsContext } from '@/contexts/IntegrationSettingsContext';

export function IntegrationSettingsHeaderActions() {
  const { onAddIntegration } = useIntegrationSettingsContext();

  return (
    <Button onClick={onAddIntegration} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      Add Integration
    </Button>
  );
}
