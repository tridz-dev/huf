import { useResourceAccess } from '@/hooks/permissions/useResourceAccess';
import { Plus } from 'lucide-react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from './ui/button';

export function KnowledgeHeaderActions() {
  const navigate = useNavigate();

  const { canCreate } = useResourceAccess('knowledge');
  const handleNew = () => {
    navigate('/knowledge?new=1');
  };

  if (!canCreate) return null;

  return (
    <Button variant="display" onClick={handleNew} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      New knowledge source
    </Button>
  );
}

/** /knowledge/new is now a dialog on /knowledge; keep the old URL (and ?agent) working. */
export function NewKnowledgeRedirect() {
  const [params] = useSearchParams();
  const next = new URLSearchParams(params);
  next.set('new', '1');
  return <Navigate to={`/knowledge?${next.toString()}`} replace />;
}
