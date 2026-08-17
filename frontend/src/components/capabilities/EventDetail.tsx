import { useState } from 'react';
import { ArrowLeft, Loader2, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { previewTriggerPayload } from '@/services/capabilityApi';
import type { CapabilityDescriptor } from '@/types/capability.types';

interface EventDetailProps {
  app: string;
  capability: CapabilityDescriptor;
  onUseEvent: (triggerPayload: Record<string, unknown>) => void;
  onBack?: () => void;
}

export function EventDetail({ app, capability, onUseEvent, onBack }: EventDetailProps) {
  const [condition, setCondition] = useState('');
  const [promptField, setPromptField] = useState('');
  const [loading, setLoading] = useState(false);

  const handleUseEvent = async () => {
    if (!capability.resource_doctype) return;

    setLoading(true);
    try {
      const payload = await previewTriggerPayload(
        app,
        capability.resource_doctype,
        capability.id,
        condition || undefined,
        promptField || undefined,
      );
      onUseEvent(payload);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        {onBack && (
          <Button size="icon-sm" variant="ghost" onClick={onBack} type="button">
            <ArrowLeft className="w-4 h-4" />
          </Button>
        )}
        <h3 className="font-medium text-sm">Configure event</h3>
      </div>

      <Card>
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

      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="event-condition">Condition (optional)</Label>
          <Input
            id="event-condition"
            placeholder="e.g. doc.status == 'Approved'"
            value={condition}
            onChange={(e) => setCondition(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="event-prompt-field">Prompt field (optional)</Label>
          <Input
            id="event-prompt-field"
            placeholder="Field to include as context in the prompt"
            value={promptField}
            onChange={(e) => setPromptField(e.target.value)}
          />
        </div>
      </div>

      <Button onClick={handleUseEvent} disabled={loading} type="button">
        {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
        Use this event
      </Button>
    </div>
  );
}
