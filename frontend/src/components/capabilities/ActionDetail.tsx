import { useEffect, useState } from 'react';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';
import { CapabilityBadges } from './CapabilityBadges';
import { describeAppAction } from '@/services/capabilityApi';
import type { CapabilityDescriptor } from '@/types/capability.types';

interface ActionDetailProps {
  capability: CapabilityDescriptor;
  onAdd: (capability: CapabilityDescriptor) => void;
  onBack?: () => void;
  className?: string;
}

export function ActionDetail({ capability, onAdd, onBack, className }: ActionDetailProps) {
  const [detail, setDetail] = useState<CapabilityDescriptor>(capability);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    describeAppAction(capability.id)
      .then((result) => {
        if (!cancelled && result) {
          setDetail(result);
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
  }, [capability.id]);

  const parameters = detail.parameters_schema || [];

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      {onBack && (
        <Button variant="ghost" size="sm" className="self-start gap-1.5" onClick={onBack}>
          <ArrowLeft className="h-3.5 w-3.5" />
          Back
        </Button>
      )}

      <div className="flex flex-col gap-1.5">
        <h3 className="text-base font-medium">{detail.title}</h3>
        {detail.description && (
          <p className="text-sm text-muted-foreground">{detail.description}</p>
        )}
        <CapabilityBadges capability={detail} />
        {detail.function_path && (
          <p className="mt-0.5 font-mono text-[10px] text-steel-soft">{detail.function_path}</p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <h4 className="text-sm font-medium">Parameters</h4>
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-steel-soft">
            <Spinner />
            Loading parameters...
          </div>
        ) : parameters.length === 0 ? (
          <p className="text-sm text-steel">This action takes no parameters.</p>
        ) : (
          <div className="flex flex-col divide-y divide-line rounded-lg border">
            {parameters.map((parameter) => (
              <div key={parameter.name} className="flex flex-col gap-0.5 p-3">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs">{parameter.name}</span>
                  <span className="text-[10px] uppercase tracking-wide text-steel-soft">
                    {parameter.type}
                  </span>
                  {parameter.required && (
                    <span className="text-[10px] uppercase tracking-wide text-destructive">
                      required
                    </span>
                  )}
                </div>
                {parameter.description && (
                  <p className="text-xs text-muted-foreground">{parameter.description}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <Button onClick={() => onAdd(detail)} disabled={loading} className="self-start">
        Add to Agent
      </Button>
    </div>
  );
}
