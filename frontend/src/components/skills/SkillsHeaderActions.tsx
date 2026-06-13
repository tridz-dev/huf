import { useState } from 'react';
import { Plus, Download, Store } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { SkillImportModal } from './SkillImportModal';
import { SkillMarketplaceModal } from './SkillMarketplaceModal';

interface SkillsHeaderActionsProps {
  onImportSuccess?: () => void;
}

export function SkillsHeaderActions({ onImportSuccess }: SkillsHeaderActionsProps) {
  const navigate = useNavigate();
  const [importOpen, setImportOpen] = useState(false);
  const [marketplaceOpen, setMarketplaceOpen] = useState(false);

  return (
    <>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setMarketplaceOpen(true)}>
          <Store className="w-4 h-4 mr-2" />
          Marketplace
        </Button>
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
      <SkillMarketplaceModal
        open={marketplaceOpen}
        onOpenChange={setMarketplaceOpen}
        onSuccess={onImportSuccess}
      />
    </>
  );
}

export default SkillsHeaderActions;
