import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useIntegrationServicesContext } from '@/contexts/IntegrationServicesContext';

export function IntegrationServicesHeaderActions() {
  const { onAddService } = useIntegrationServicesContext();
  const navigate = useNavigate();

  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" size="sm" onClick={() => navigate('/integrations')}>
        Integrations
      </Button>
      <Button variant="display" onClick={onAddService} size="sm">
        <Plus className="w-4 h-4 mr-2" />
        Add Service
      </Button>
    </div>
  );
}
