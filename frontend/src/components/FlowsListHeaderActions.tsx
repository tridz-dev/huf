import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from './ui/button';
import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { NewFlowDialog } from './flow/list/NewFlowDialog';

/** The list's one primary action. It opens the chooser: start from scratch, or copy a ready-made template. */
export function FlowsListHeaderActions() {
  const [open, setOpen] = useState(false);
  const { canCreate } = useFlowPermissions();

  if (!canCreate) return null;

  return (
    <>
      <Button variant="display" data-testid="flow-new" onClick={() => setOpen(true)} size="sm">
        <Plus className="w-4 h-4 mr-2" />
        New flow
      </Button>
      <NewFlowDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
