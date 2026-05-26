import { useState } from 'react';
import { Plus, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';
import { useFlowContext } from '../contexts/FlowContext';
import { toast } from 'sonner';

export function FlowsListHeaderActions() {
  const navigate = useNavigate();
  const { createFlow } = useFlowContext();
  const [creating, setCreating] = useState(false);

  const handleNewFlow = async () => {
    try {
      setCreating(true);
      const newFlow = await createFlow('New Flow', 'Uncategorized');
      navigate(`/flows/${newFlow.id}`);
    } catch (err) {
      toast.error('Failed to create flow', {
        description: err instanceof Error ? err.message : 'Unknown error',
      });
    } finally {
      setCreating(false);
    }
  };

  return (
    <Button onClick={handleNewFlow} size="sm" disabled={creating}>
      {creating ? (
        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
      ) : (
        <Plus className="w-4 h-4 mr-2" />
      )}
      {creating ? 'Creating...' : 'New Flow'}
    </Button>
  );
}
