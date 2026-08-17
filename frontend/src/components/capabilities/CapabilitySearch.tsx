import { useEffect, useState } from 'react';
import { Search } from 'lucide-react';
import { toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { useDebounce } from '@/hooks/useDebounce';
import { CapabilityCard } from './CapabilityCard';
import { searchAppActions } from '@/services/capabilityApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { CapabilityDescriptor } from '@/types/capability.types';

interface CapabilitySearchProps {
  app: string;
  onSelectAction: (capability: CapabilityDescriptor) => void;
  className?: string;
}

export function CapabilitySearch({ app, onSelectAction, className }: CapabilitySearchProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<CapabilityDescriptor[]>([]);
  const [loading, setLoading] = useState(true);
  const debouncedQuery = useDebounce(query, 300);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    searchAppActions(app, debouncedQuery)
      .then((result) => {
        if (!cancelled) {
          setResults(result);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          console.error('Error searching app actions:', error);
          const errorMessage = getFrappeErrorMessage(error);
          toast.error(errorMessage || 'Failed to search actions');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [app, debouncedQuery]);

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-steel-soft" />
        <Input
          placeholder="Search actions..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="pl-9"
        />
      </div>

      <div className="flex flex-col gap-2">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-sm text-steel-soft">Searching actions...</div>
          </div>
        ) : results.length === 0 ? (
          <div className="flex items-center justify-center py-12">
            <div className="text-sm text-steel">
              {query ? 'No actions match your search' : 'No actions available'}
            </div>
          </div>
        ) : (
          results.map((capability) => (
            <CapabilityCard
              key={capability.id}
              capability={capability}
              onSelect={onSelectAction}
            />
          ))
        )}
      </div>
    </div>
  );
}
