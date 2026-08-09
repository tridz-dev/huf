import { useEffect, useState } from 'react';
import { ArrowLeft, Loader2, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { CapabilityCard } from './CapabilityCard';
import { describeResource } from '@/services/capabilityApi';
import type { CapabilityDescriptor, CapabilityResourceDetail } from '@/types/capability.types';

interface ResourceDetailProps {
  app: string;
  doctype: string;
  onSelectAction: (capability: CapabilityDescriptor) => void;
  onSelectEvent: (capability: CapabilityDescriptor) => void;
  onBack?: () => void;
}

export function ResourceDetail({
  app,
  doctype,
  onSelectAction,
  onSelectEvent,
  onBack,
}: ResourceDetailProps) {
  const [detail, setDetail] = useState<CapabilityResourceDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setDetail(null);

    describeResource(app, doctype).then((result) => {
      setDetail(result || null);
      setLoading(false);
    });
  }, [app, doctype]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-5 h-5 animate-spin text-steel-soft" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="text-center py-12 border border-dashed rounded-none bg-paper-deep/20">
        <p className="font-body text-steel-soft">Could not load resource details.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        {onBack && (
          <Button size="icon-sm" variant="ghost" onClick={onBack} type="button">
            <ArrowLeft className="w-4 h-4" />
          </Button>
        )}
        <div>
          <h3 className="font-medium text-sm">{detail.title}</h3>
          {detail.fields_summary && (
            <p className="text-xs text-steel-soft">{detail.fields_summary}</p>
          )}
        </div>
      </div>

      <div className="space-y-3">
        <h4 className="text-xs font-mono uppercase tracking-wide text-steel-soft">Actions</h4>
        {detail.generated_actions.length === 0 ? (
          <p className="text-sm text-steel-soft">No actions available for this resource.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {detail.generated_actions.map((capability) => (
              <CapabilityCard
                key={capability.id}
                capability={capability}
                onSelect={onSelectAction}
              />
            ))}
          </div>
        )}
      </div>

      <div className="space-y-3">
        <h4 className="text-xs font-mono uppercase tracking-wide text-steel-soft">Events</h4>
        {detail.generated_events.length === 0 ? (
          <p className="text-sm text-steel-soft">No events available for this resource.</p>
        ) : (
          <div className="space-y-2">
            {detail.generated_events.map((capability) => (
              <Card
                key={capability.id}
                role="button"
                tabIndex={0}
                onClick={() => onSelectEvent(capability)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectEvent(capability);
                  }
                }}
                className="cursor-pointer hover:bg-paper-deep transition-colors"
              >
                <CardHeader className="p-3">
                  <div className="flex items-center gap-2">
                    <Zap className="w-4 h-4 text-steel-soft shrink-0" />
                    <CardTitle className="text-sm">{capability.title}</CardTitle>
                  </div>
                  {capability.short_description && (
                    <CardDescription className="text-xs">
                      {capability.short_description}
                    </CardDescription>
                  )}
                </CardHeader>
              </Card>
            ))}
          </div>
        )}
      </div>

      {detail.related_resources && detail.related_resources.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-mono uppercase tracking-wide text-steel-soft">
            Related resources
          </h4>
          <div className="flex items-center gap-2 flex-wrap">
            {detail.related_resources.map((related) => (
              <Badge key={related} variant="outline">
                {related}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
