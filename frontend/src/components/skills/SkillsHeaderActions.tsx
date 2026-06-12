import { useState } from 'react';
import { Plus, Download } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { SkillImportModal } from './SkillImportModal';

interface SkillsHeaderActionsProps {
  onImportSuccess?: () => void;
}

export function SkillsHeaderActions({ onImportSuccess }: SkillsHeaderActionsProps) {
  const navigate = useNavigate();
  const [importOpen, setImportOpen] = useState(false);

  return (
    <>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
          <Download className="w-4 h-4 mr-2" />
          Import
        </Button>
        <Button size="sm" onClick={() => navigate('/skills/new')}>
          <Plus className="w-4 h-4 mr-2" />
          New Skill
        </Button>
      </div>
      <SkillImportModal open={importOpen} onOpenChange={setImportOpen} onSuccess={onImportSuccess} />
    </>
  );
}

export default SkillsHeaderActions;
