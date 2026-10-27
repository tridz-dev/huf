import { Field } from '@/components/ui/field';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import type { GatewayDoc } from '@/services/gatewayApi';

/** Gateway fields only Slack uses; saved with the rest of the channel settings. */
export const SLACK_GATEWAY_FIELDS = ['unmapped_policy', 'private_reply_policy', 'show_feedback_buttons'] as const;

export function slackSaveFields(gateway: GatewayDoc): Partial<GatewayDoc> {
  if (gateway.provider !== 'Slack') return {};
  return Object.fromEntries(SLACK_GATEWAY_FIELDS.map((f) => [f, gateway[f] ?? null]));
}

interface Props {
  gateway: GatewayDoc;
  onChange: (patch: Partial<GatewayDoc>) => void;
}

export function SlackPolicySection({ gateway, onChange }: Props) {
  if (gateway.provider !== 'Slack') return null;
  return (
    <div className="grid gap-3 rounded-lg border p-4">
      <p className="text-sm font-medium">Slack people and answers</p>
      <Field
        label="When a person is not linked"
        hint="Ask sends a one-time link to connect their account. The other option runs them as the Run as user."
        size="sm"
      >
        {(fp) => (
          <Select
            value={gateway.unmapped_policy || 'Ask to link account'}
            onValueChange={(v) => onChange({ unmapped_policy: v as GatewayDoc['unmapped_policy'] })}
          >
            <SelectTrigger {...fp}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Ask to link account">Ask to link account</SelectItem>
              <SelectItem value="Use service user">Use service user</SelectItem>
            </SelectContent>
          </Select>
        )}
      </Field>
      <Field label="Where to send answers" hint="Private answers are sent as a direct message. Needs the im:write Slack permission." size="sm">
        {(fp) => (
          <Select
            value={gateway.private_reply_policy || 'Reply where asked'}
            onValueChange={(v) => onChange({ private_reply_policy: v as GatewayDoc['private_reply_policy'] })}
          >
            <SelectTrigger {...fp}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Reply where asked">Reply where asked</SelectItem>
              <SelectItem value="Private when marked sensitive">Private when marked sensitive</SelectItem>
              <SelectItem value="Always private">Always private</SelectItem>
            </SelectContent>
          </Select>
        )}
      </Field>
      <Field
        label="Ask for feedback after answers"
        hint="Posts a thumbs up / thumbs down question in the thread."
        size="sm"
        id="channel-slack-feedback"
      >
        <div className="flex h-control-md items-center">
          <Switch
            id="channel-slack-feedback"
            checked={Boolean(gateway.show_feedback_buttons)}
            onCheckedChange={(checked) => onChange({ show_feedback_buttons: checked ? 1 : 0 })}
          />
        </div>
      </Field>
    </div>
  );
}
