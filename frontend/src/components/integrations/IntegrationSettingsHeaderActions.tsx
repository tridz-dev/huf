import { Plus, Layers } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../ui/button';
import { useIntegrationSettingsContext } from '@/contexts/IntegrationSettingsContext';

export function IntegrationSettingsHeaderActions({
  kind = 'integrations',
}: {
  kind?: 'channels' | 'integrations';
}) {
  const { onAddIntegration } = useIntegrationSettingsContext();
  const navigate = useNavigate();

  return (
    <div className="flex items-center gap-2">
      {kind === 'integrations' && <Button variant="outline" size="sm" onClick={() => navigate('/integration-services')}>
        <Layers className="w-4 h-4 mr-2" />
        Service catalog
      </Button>}
      <Button variant="display" onClick={onAddIntegration} size="sm">
        <Plus className="w-4 h-4 mr-2" />
        {kind === 'channels' ? 'Add Channel' : 'Add Integration'}
      </Button>
    </div>
  );
}
