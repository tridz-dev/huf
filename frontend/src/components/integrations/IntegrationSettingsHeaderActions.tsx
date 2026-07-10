import { Plus, Layers } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../ui/button';
import { useIntegrationSettingsContext } from '@/contexts/IntegrationSettingsContext';

export function IntegrationSettingsHeaderActions() {
  const { onAddIntegration } = useIntegrationSettingsContext();
  const navigate = useNavigate();

  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" onClick={() => navigate('/integration-services')}>
        <Layers className="w-4 h-4 mr-2" />
        Service Catalog
      </Button>
      <Button onClick={onAddIntegration} size="sm">
        <Plus className="w-4 h-4 mr-2" />
        Add Integration
      </Button>
    </div>
  );
}
