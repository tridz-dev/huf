import { Badge } from '@/components/ui/badge';
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AttachableSource } from './useAttachableSources';
import { HEALTH_BADGE, HEALTH_HINT, HEALTH_LABEL, isAttachable, searchMethodLabel } from './sourceHealth';

interface Props {
  sources: AttachableSource[];
  value: string;
  onChange: (name: string) => void;
  loading?: boolean;
}

export function KnowledgeSourcePicker({ sources, value, onChange, loading }: Props) {
  return (
    <Command className="rounded-md border">
      <CommandInput placeholder="Search knowledge sources..." />
      <CommandList className="max-h-56">
        <CommandEmpty>{loading ? 'Loading...' : 'No knowledge sources found.'}</CommandEmpty>
        {sources.map((s) => {
          const ok = isAttachable(s.health) || s.name === value;
          const docs = s.counts.total;
          return (
            <CommandItem
              key={s.name}
              value={`${s.label} ${s.name}`}
              disabled={!ok}
              onSelect={() => ok && onChange(s.name)}
              className={cn('flex items-start gap-2', !ok && 'opacity-60')}
            >
              <Check className={cn('mt-0.5 h-4 w-4 shrink-0', value === s.name ? 'opacity-100' : 'opacity-0')} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium">{s.label}</span>
                  <Badge variant={HEALTH_BADGE[s.health]} className="shrink-0">
                    {HEALTH_LABEL[s.health]}
                  </Badge>
                </div>
                <p className="text-xs text-steel-soft">
                  {docs} {docs === 1 ? 'document' : 'documents'} · {searchMethodLabel(s.knowledgeType)}
                </p>
                {s.health === 'attention' && (
                  <p className="text-xs text-steel-soft">Some documents could not be read; the rest are searchable</p>
                )}
                {!ok && <p className="text-xs text-steel-soft">Cannot be added: {HEALTH_HINT[s.health]}</p>}
              </div>
            </CommandItem>
          );
        })}
      </CommandList>
    </Command>
  );
}
