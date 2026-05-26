import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';

export function KnowledgeHeaderActions() {
  const navigate = useNavigate();

  const handleNew = () => {
    navigate('/knowledge/new');
  };

  return (
    <Button onClick={handleNew} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      New Knowledge Source
    </Button>
  );
}
