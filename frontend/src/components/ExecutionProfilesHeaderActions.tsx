import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export function ExecutionProfilesHeaderActions() {
  const navigate = useNavigate();

  const handleNewProfile = () => {
    navigate('/execution-profiles/new');
  };

  return (
    <Button variant="display" onClick={handleNewProfile}>
      <Plus className="mr-2 h-4 w-4" />
      New Execution Profile
    </Button>
  );
}
