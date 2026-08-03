import { Plus, Link2 } from 'lucide-react';
import { Button } from './ui/button';
import { useAiProviders } from '../contexts/AiProvidersContext';
import { useNavigate } from 'react-router-dom';

export function AiProvidersHeaderActions() {
  const { onAddProvider } = useAiProviders();
  const navigate = useNavigate();

  return (
    <div className="flex items-center gap-2">
      <Button variant="outline" onClick={() => navigate('/provider-connections')} size="sm">
        <Link2 className="w-4 h-4 mr-2" />
        Connections
      </Button>
      <Button variant="display" onClick={onAddProvider} size="sm">
        <Plus className="w-4 h-4 mr-2" />
        Add Provider
      </Button>
    </div>
  );
}
