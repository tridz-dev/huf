import { useEffect, useState } from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { cn } from '@/lib/utils';

interface SubscriptionRuntimeOption {
  name: string;
  runtime_name: string;
}

interface SubscriptionRuntimeSelectProps {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  required?: boolean;
  className?: string;
}

/**
 * Link-field style picker for the Subscription Runtime doctype, modeled on
 * ProviderBrandSelect: fetches the list of runtimes and renders them as a
 * standard shadcn Select bound to the linked doc's name.
 */
export function SubscriptionRuntimeSelect({
  value,
  onChange,
  label = 'Subscription Runtime',
  required = false,
  className,
}: SubscriptionRuntimeSelectProps) {
  const [runtimes, setRuntimes] = useState<SubscriptionRuntimeOption[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    db.getDocList(doctype['Subscription Runtime'], {
      fields: ['name', 'runtime_name'],
      limit: 200,
    })
      .then((rows) => {
        if (cancelled) return;
        setRuntimes(
          (rows as Record<string, unknown>[]).map((r) => ({
            name: r.name as string,
            runtime_name: (r.runtime_name as string) || (r.name as string),
          })),
        );
      })
      .catch((error) => {
        console.error('Error fetching subscription runtimes:', error);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className={cn('space-y-2', className)}>
      <Label>
        {label}
        {required ? <span className="text-destructive"> *</span> : null}
      </Label>
      <Select value={value || undefined} onValueChange={onChange}>
        <SelectTrigger>
          <SelectValue
            placeholder={loading ? 'Loading runtimes...' : 'Select a subscription runtime'}
          />
        </SelectTrigger>
        <SelectContent>
          {runtimes.map((runtime) => (
            <SelectItem key={runtime.name} value={runtime.name}>
              {runtime.runtime_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {!loading && runtimes.length === 0 && (
        <p className="text-xs text-muted-foreground">
          No subscription runtimes configured yet.
        </p>
      )}
    </div>
  );
}
