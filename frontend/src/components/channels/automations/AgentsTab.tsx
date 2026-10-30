import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { RoutingOrderCard } from '@/components/whatsapp/overview/RoutingOrderCard';
import { SolutionsOnNumberCard } from '@/components/whatsapp/overview/SolutionsOnNumberCard';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { getNumberSummary, pauseSolution, resumeSolution } from '@/services/solutionsApi';
import type { NumberSummary } from '@/types/solutions';

export function AgentsTab({ gw }: { gw: string }) {
  const [summary, setSummary] = useState<NumberSummary | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => getNumberSummary(gw).then(setSummary).catch((e) => setError(getFrappeErrorMessage(e))), [gw]);
  useEffect(() => { setSummary(null); void load(); }, [load]);

  if (!summary) return error ? <p role="alert" className="text-sm text-destructive">{error}</p> : <p className="text-sm text-steel">Loading...</p>;

  const toggle = async (name: string, on: boolean) => {
    try {
      await (on ? resumeSolution(name) : pauseSolution(name));
      await load();
    } catch (e) {
      toast.error(getFrappeErrorMessage(e));
    }
  };
  return (
    <div className="grid gap-4">
      <SolutionsOnNumberCard gateway={gw} summary={summary} />
      <div className="flex flex-wrap gap-4 text-sm">
        {summary.solutions.map((s) => (
          <Label key={s.name} weight="normal" className="flex items-center gap-2 text-ink">
            <Switch aria-label={`${s.title} live`} checked={s.status === 'Live'} onCheckedChange={(c) => void toggle(s.name, c)} />
            {s.title}: {s.status === 'Live' ? 'Live' : 'Off'}
          </Label>
        ))}
      </div>
      <RoutingOrderCard summary={summary} />
    </div>
  );
}
