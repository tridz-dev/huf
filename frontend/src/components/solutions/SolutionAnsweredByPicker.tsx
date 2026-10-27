import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { updateSolution } from '@/services/solutionsApi';
import { loadTargets, type TargetOption } from './targets';

interface Props {
  solution: string;
  current?: { type: 'Agent' | 'Flow'; name: string } | null;
  onSaved: () => void;
  onCancel?: () => void;
}

const nativeSelect =
  'h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/** Picks the agent or flow that answers a solution and saves it with updateSolution. */
export function SolutionAnsweredByPicker({ solution, current, onSaved, onCancel }: Props) {
  const [targets, setTargets] = useState<TargetOption[]>([]);
  const [value, setValue] = useState(current ? `${current.type}:${current.name}` : '');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadTargets().then((t) => !cancelled && setTargets(t));
    return () => {
      cancelled = true;
    };
  }, []);

  const save = async () => {
    const [type, ...rest] = value.split(':');
    const name = rest.join(':');
    if (!type || !name) return;
    setBusy(true);
    try {
      await updateSolution(
        solution,
        type === 'Flow'
          ? { primary_target_type: 'Flow', primary_flow: name }
          : { primary_target_type: 'Agent', primary_agent: name },
      );
      toast.success('Answered by saved.');
      onSaved();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not save.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label htmlFor="answered-by-select" className="sr-only">
        Answered by
      </label>
      <select id="answered-by-select" className={nativeSelect} value={value} onChange={(e) => setValue(e.target.value)}>
        <option value="">{targets.length === 0 ? 'No agents or flows yet' : 'Choose an agent or flow'}</option>
        {targets.map((t) => (
          <option key={`${t.type}:${t.name}`} value={`${t.type}:${t.name}`}>
            {t.label} ({t.type.toLowerCase()})
          </option>
        ))}
      </select>
      <Button size="sm" disabled={busy || !value} onClick={() => void save()}>
        Save
      </Button>
      {onCancel ? (
        <Button size="sm" variant="outline" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      ) : null}
    </div>
  );
}
