import { Field, FieldRow } from '@/components/ui/field';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import type { GatewayDoc, GatewayPolicy } from '@/services/gatewayApi';

interface RoomPolicySectionProps {
  gateway: GatewayDoc;
  onChange: (patch: Partial<GatewayDoc>) => void;
}

/** GW-18: room/group-chat admission policy (hidden for WhatsApp by the caller). */
export function RoomPolicySection({ gateway, onChange }: RoomPolicySectionProps) {
  return (
    <div className="grid gap-3 rounded-lg border p-4">
      <p className="text-sm font-medium">Room &amp; group chat admission</p>
      <p className="text-xs text-muted-foreground">
        Controls how this channel admits messages from rooms, channels, or group chats
        (as opposed to one-on-one direct messages, which use the policy above).
      </p>
      <FieldRow cols={2}>
        <Field label="Room policy" size="sm">
          {(fp) => (
            <Select
              value={gateway.room_policy || 'Allow list'}
              onValueChange={(v) => onChange({ room_policy: v as GatewayPolicy })}
            >
              <SelectTrigger {...fp}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Allow list">Allow list — require an approved room</SelectItem>
                <SelectItem value="Disabled">Disabled — reject room messages</SelectItem>
              </SelectContent>
            </Select>
          )}
        </Field>
        <Field label="Sender policy within a room" size="sm">
          {(fp) => (
            <Select
              value={gateway.room_sender_policy || 'Allow list'}
              onValueChange={(v) => onChange({ room_sender_policy: v as GatewayPolicy })}
            >
              <SelectTrigger {...fp}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Allow list">Allow list — require an approved sender</SelectItem>
              </SelectContent>
            </Select>
          )}
        </Field>
      </FieldRow>
      <FieldRow cols={2}>
        <Field
          label="Require @mention in rooms"
          size="sm"
          hint="Only respond when the bot is explicitly mentioned"
          id="channel-mention-required"
        >
          <div className="flex h-control-md items-center">
            <Switch
              id="channel-mention-required"
              checked={Boolean(gateway.mention_required)}
              onCheckedChange={(checked) => onChange({ mention_required: checked ? 1 : 0 })}
            />
          </div>
        </Field>
      </FieldRow>
    </div>
  );
}
