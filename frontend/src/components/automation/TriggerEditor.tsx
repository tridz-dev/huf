import { useEffect, useState } from 'react';
import { Copy } from 'lucide-react';
import { toast } from 'sonner';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { getDocTypes } from '@/services/agentApi';
import { TriggerFieldsRenderer } from './TriggerFieldsRenderer';
import { TriggerDocEventExtras } from './TriggerDocEventExtras';
import { AUTOMATION_TRIGGER_TYPES, triggerTypeHelpText } from './TriggerFieldsConfig';
import type {
  AutomationTrigger,
  AutomationTriggerAttachment,
  AutomationTriggerType,
} from '@/types/automation.types';

/**
 * Automation-scoped trigger data as edited in the form: same shape as the
 * `Automation Trigger` doctype, but `trigger_type` is always present (a row
 * being edited always has one, even before it's saved) and `webhook_key`
 * may be populated in-memory right after `create_trigger` returns it -- the
 * backend never returns it again afterwards (`list_triggers` omits the
 * field entirely), so once this component is re-mounted from a fresh fetch
 * the value legitimately disappears. That's the intended "shown once"
 * behavior, not a bug.
 */
export type EditableAutomationTrigger = Partial<AutomationTrigger> & {
  trigger_type: AutomationTriggerType;
};

export interface TriggerEditorPermissions {
  /** False when the user can view but not modify this trigger (e.g. a
   * locked system agent's automations, or a trigger the user only has
   * read access to). */
  canEdit: boolean;
}

export interface TriggerEditorProps {
  trigger: EditableAutomationTrigger;
  onChange: (patch: Partial<EditableAutomationTrigger>) => void;
  permissions: TriggerEditorPermissions;
}

const WEBHOOK_ENDPOINT_PATH = '/api/method/huf.ai.automation_webhook.handle_automation_webhook';

/**
 * Editor for a single Automation Trigger's fields, keyed off `trigger_type`.
 * Refactored from the legacy Agent-scoped `TriggerModal.tsx` +
 * `TriggerFieldsRenderer.tsx` + `TriggerDocEventExtras.tsx` trio
 * (`components/agent/`) -- same field-rendering logic and styling, but this
 * version has no `agentId` dependency and is meant to be embedded directly
 * in a page (not a modal), since `AutomationFormPage.tsx` edits 0-N triggers
 * inline rather than one trigger per dialog.
 */
export function TriggerEditor({ trigger, onChange, permissions }: TriggerEditorProps) {
  const [docTypes, setDocTypes] = useState<Array<{ name: string }>>([]);
  const [loadingDocTypes, setLoadingDocTypes] = useState(false);
  const disabled = !permissions.canEdit;

  useEffect(() => {
    if (trigger.trigger_type !== 'Doc Event') return;
    let cancelled = false;
    setLoadingDocTypes(true);
    getDocTypes()
      .then((result) => {
        if (!cancelled) setDocTypes(result || []);
      })
      .finally(() => {
        if (!cancelled) setLoadingDocTypes(false);
      });
    return () => {
      cancelled = true;
    };
  }, [trigger.trigger_type]);

  const handleFieldChange = (field: string, value: string | number | undefined) => {
    onChange({ [field]: value } as Partial<EditableAutomationTrigger>);
  };

  const handleCopyWebhookUrl = () => {
    if (!trigger.webhook_slug) return;
    const url = `${window.location.origin}${WEBHOOK_ENDPOINT_PATH}?slug=${encodeURIComponent(trigger.webhook_slug)}`;
    navigator.clipboard
      .writeText(url)
      .then(() => toast.success('Webhook URL copied'))
      .catch(() => toast.error('Could not copy webhook URL'));
  };

  const handleCopyWebhookKey = () => {
    if (!trigger.webhook_key) return;
    navigator.clipboard
      .writeText(trigger.webhook_key)
      .then(() => toast.success('Webhook key copied'))
      .catch(() => toast.error('Could not copy webhook key'));
  };

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Trigger type</Label>
        <Select
          onValueChange={(value) => onChange({ trigger_type: value as AutomationTriggerType })}
          value={trigger.trigger_type}
          disabled={disabled}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {AUTOMATION_TRIGGER_TYPES.map((type) => (
              <SelectItem key={type} value={type}>
                {type}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-steel-soft">{triggerTypeHelpText[trigger.trigger_type]}</p>
      </div>

      <div className="flex flex-row items-center justify-between rounded-md border p-4">
        <div className="space-y-0.5">
          <Label className="text-sm">Enabled</Label>
          <p className="text-xs text-steel-soft">Turn this trigger off without deleting it.</p>
        </div>
        <Switch
          checked={trigger.disabled !== 1}
          onCheckedChange={(checked) => onChange({ disabled: checked ? 0 : 1 })}
          disabled={disabled}
        />
      </div>

      {trigger.trigger_type === 'Schedule' && (
        <div className="space-y-1.5">
          <Label>Execution mode</Label>
          <Select
            onValueChange={(value) => onChange({ execution_mode: value as AutomationTrigger['execution_mode'] })}
            value={trigger.execution_mode || 'Realtime'}
            disabled={disabled}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Realtime">Instant</SelectItem>
              <SelectItem value="Batch">Batch</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-steel-soft">
            {trigger.execution_mode === 'Batch'
              ? 'Runs later today instead of immediately, at a lower cost.'
              : 'Runs as soon as the schedule fires.'}
          </p>
        </div>
      )}

      {(trigger.trigger_type === 'Schedule' ||
        trigger.trigger_type === 'App Event' ||
        trigger.trigger_type === 'Doc Event') && (
        <TriggerFieldsRenderer
          triggerType={trigger.trigger_type}
          values={trigger as unknown as Record<string, unknown>}
          onFieldChange={handleFieldChange}
          docTypes={docTypes}
          loadingDocTypes={loadingDocTypes}
          disabled={disabled}
        />
      )}

      {trigger.trigger_type === 'Doc Event' && (
        <TriggerDocEventExtras
          referenceDoctype={trigger.reference_doctype}
          promptField={trigger.prompt_field}
          promptFieldMode={trigger.prompt_field_mode}
          fileAttachments={trigger.file_attachments || []}
          onPromptFieldChange={(value) => onChange({ prompt_field: value })}
          onPromptFieldModeChange={(value) =>
            onChange({ prompt_field_mode: value as AutomationTrigger['prompt_field_mode'] })
          }
          onFileAttachmentsChange={(rows: AutomationTriggerAttachment[]) => onChange({ file_attachments: rows })}
          disabled={disabled}
        />
      )}

      {trigger.trigger_type === 'Webhook' && (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Webhook URL</Label>
            {trigger.webhook_slug ? (
              <div className="flex items-center gap-2">
                <Input
                  readOnly
                  value={`${WEBHOOK_ENDPOINT_PATH}?slug=${trigger.webhook_slug}`}
                  className="font-mono text-xs"
                />
                <Button type="button" variant="outline" size="icon" onClick={handleCopyWebhookUrl}>
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <p className="text-sm text-steel-soft rounded-md border border-dashed p-3">
                Save this automation to generate a webhook URL and secret key.
              </p>
            )}
            <p className="text-xs text-steel-soft">
              An external service calls this URL (GET or POST) to run this automation.
            </p>
          </div>

          {trigger.webhook_slug && (
            <div className="space-y-1.5">
              <Label>Webhook key</Label>
              {trigger.webhook_key ? (
                <>
                  <div className="flex items-center gap-2">
                    <Input readOnly value={trigger.webhook_key} className="font-mono text-xs" />
                    <Button type="button" variant="outline" size="icon" onClick={handleCopyWebhookKey}>
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                  <p className="text-xs text-warning">
                    Copy this now -- it will not be shown again. Send it as an{' '}
                    <code className="font-mono">X-Webhook-Key</code> header on every call.
                  </p>
                </>
              ) : (
                <p className="text-sm text-steel-soft rounded-md border border-dashed p-3">
                  Key generated and stored -- hidden after creation. To rotate it, delete this trigger
                  and add a new one.
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {trigger.trigger_type === 'Manual' && (
        <p className="text-sm text-steel-soft rounded-lg border p-4">{triggerTypeHelpText.Manual}</p>
      )}
    </div>
  );
}
