import { useEffect, useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { getCapabilityApps } from '@/services/capabilityApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { CapabilityApp } from '@/types/capability.types';

interface AppPickerProps {
  onSelect: (app: CapabilityApp) => void;
  className?: string;
}

export function AppPicker({ onSelect, className }: AppPickerProps) {
  const [apps, setApps] = useState<CapabilityApp[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getCapabilityApps()
      .then((result) => {
        if (!cancelled) {
          setApps(result);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          console.error('Error loading capability apps:', error);
          const errorMessage = getFrappeErrorMessage(error);
          toast.error(errorMessage || 'Failed to load apps');
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
  }, []);

  const filteredApps = useMemo(() => {
    if (!searchQuery) return apps;
    const query = searchQuery.toLowerCase();
    return apps.filter(
      (app) => app.title.toLowerCase().includes(query) || app.app.toLowerCase().includes(query)
    );
  }, [apps, searchQuery]);

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-steel-soft" />
        <Input
          placeholder="Search apps..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-9"
        />
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {loading ? (
          <div className="col-span-full flex items-center justify-center py-12">
            <div className="text-sm text-steel-soft">Loading apps...</div>
          </div>
        ) : filteredApps.length === 0 ? (
          <div className="col-span-full flex items-center justify-center py-12">
            <div className="text-sm text-steel">
              {searchQuery ? 'No apps match your search' : 'No apps available'}
            </div>
          </div>
        ) : (
          filteredApps.map((app) => (
            <button
              key={app.app}
              type="button"
              onClick={() => onSelect(app)}
              className={cn(
                'flex flex-col items-start gap-0.5 rounded-lg border p-3 text-left transition-colors',
                'hover:bg-paper-deep',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
              )}
            >
              <span className="text-sm font-medium">{app.title}</span>
              <span className="font-mono text-[10px] text-steel-soft">{app.app}</span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
