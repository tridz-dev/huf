import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { BulkActionBar, ConfirmDestructive } from '@/components/grid';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { bulkDeleteInputs } from './inputsApi';

interface BulkDeleteInputsProps {
  knowledgeSource: string;
  /** Names of the selected inputs. */
  names: string[];
  onClear: () => void;
  /** Runs once after the batch, with the names that were deleted. */
  onDeleted: (deleted: string[]) => void;
}

const plural = (n: number) => `${n.toLocaleString()} ${n === 1 ? 'document' : 'documents'}`;

/** Floating bar plus confirmation for deleting the selected documents (documents only, never the source). */
export function BulkDeleteInputs({ knowledgeSource, names, onClear, onDeleted }: BulkDeleteInputsProps) {
  const [confirm, setConfirm] = useState(false);

  const run = async () => {
    try {
      const { deleted, failed } = await bulkDeleteInputs(knowledgeSource, names);
      if (failed.length === 0) toast.success(`Removed ${plural(deleted.length)}`);
      else if (deleted.length > 0) toast.warning(`Removed ${plural(deleted.length)}; ${failed.length.toLocaleString()} could not be removed (${failed[0].error})`);
      else toast.error(failed[0]?.error || 'Could not remove the selected documents');
      onDeleted(deleted);
    } catch (e) {
      toast.error(getFrappeErrorMessage(e) || 'Could not remove the selected documents');
    }
  };

  return (
    <>
      <BulkActionBar
        count={names.length}
        noun={['document', 'documents']}
        onClear={onClear}
        actions={[{ label: 'Delete', icon: <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />, destructive: true, onClick: () => setConfirm(true) }]}
      />
      <ConfirmDestructive
        open={confirm}
        onOpenChange={setConfirm}
        title={`Delete ${plural(names.length)}?`}
        consequence="They are removed from this source and agents can no longer use them. The source itself stays."
        recovery="This cannot be undone."
        actionLabel="Delete"
        onConfirm={run}
      />
    </>
  );
}
