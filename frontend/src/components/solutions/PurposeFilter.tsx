import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { labels, PURPOSE_LABELS } from './labels';
import type { Intent } from '@/types/solutions';

const ALL = 'all';

interface PurposeFilterProps {
  value: string;
  onChange: (purpose: string) => void;
  intents?: Intent[];
}

export function PurposeFilter({ value, onChange, intents }: PurposeFilterProps) {
  const options = intents && intents.length
    ? intents.map((i) => ({ id: i.id, name: i.name }))
    : Object.entries(PURPOSE_LABELS).filter(([id]) => id !== 'custom').map(([id, name]) => ({ id, name }));
  return (
    <Select value={value || ALL} onValueChange={(v) => onChange(v === ALL ? '' : v)}>
      <SelectTrigger className="h-9 w-[180px] text-sm" aria-label={labels.purpose}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{labels.anyPurpose}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.id} value={o.id}>
            {o.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
