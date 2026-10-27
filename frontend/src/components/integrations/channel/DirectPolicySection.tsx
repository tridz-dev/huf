import { Field, FieldRow } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { AccessTab } from '@/components/whatsapp/AccessTab';
import { OPEN_POLICY_HELPER_TEXT, directPolicyOptions } from '@/components/gateway/directPolicy';
import type { GatewayDoc, GatewayPolicy } from '@/services/gatewayApi';

interface PolicySectionProps {
  gateway: GatewayDoc;
  onChange: (patch: Partial<GatewayDoc>) => void;
}

/** Direct message policy, pairing settings and the approved-people list. */
export function DirectPolicySection({ gateway, onChange }: PolicySectionProps) {
  return (
    <>
      <Field label="Direct message policy">
        {(fp) => (
          <Select
            value={gateway.direct_policy || 'Pairing'}
            onValueChange={(v) => onChange({ direct_policy: v as GatewayPolicy })}
          >
            <SelectTrigger {...fp}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {directPolicyOptions(gateway.provider).includes('Open') && (
                <SelectItem value="Open">Open — people connect their own account first</SelectItem>
              )}
              <SelectItem value="Allow list">Allow list — require an approved contact</SelectItem>
              <SelectItem value="Pairing">Pairing — require approval for new senders</SelectItem>
              <SelectItem value="Disabled">Disabled — reject direct messages</SelectItem>
            </SelectContent>
          </Select>
        )}
      </Field>
      {directPolicyOptions(gateway.provider).includes('Open') && (
        <p className="text-xs text-muted-foreground">{OPEN_POLICY_HELPER_TEXT}</p>
      )}

      {gateway.direct_policy === 'Pairing' && (
        <div className="grid gap-3 rounded-lg border p-4">
          <div className="space-y-0.5">
            <p className="text-sm font-medium">New senders</p>
            <p className="text-xs text-muted-foreground">
              Someone who isn&apos;t approved yet gets a pairing code and waits below until you approve them.
            </p>
          </div>
          <Field
            label="Send them their pairing code"
            hint="Without it, new senders get no reply at all until you approve them."
            size="sm"
            id="channel-pairing-reply"
          >
            <div className="flex h-control-md items-center">
              <Switch
                id="channel-pairing-reply"
                checked={Boolean(gateway.pairing_reply_enabled)}
                onCheckedChange={(checked) => onChange({ pairing_reply_enabled: checked ? 1 : 0 })}
              />
            </div>
          </Field>
          <FieldRow cols={3}>
            <Field label="Code lifetime (minutes)" size="sm">
              <Input
                type="number"
                min={1}
                value={gateway.pairing_ttl_minutes ?? 60}
                onChange={(e) =>
                  onChange({ pairing_ttl_minutes: e.target.value ? Number(e.target.value) : undefined })
                }
              />
            </Field>
            <Field label="Codes sent per day" hint="0 sends none." size="sm">
              <Input
                type="number"
                min={0}
                value={gateway.pairing_reply_daily_limit ?? 20}
                onChange={(e) =>
                  onChange({
                    pairing_reply_daily_limit: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
              />
            </Field>
            <Field label="Most people waiting" hint="0 means no limit." size="sm">
              <Input
                type="number"
                min={0}
                value={gateway.pairing_pending_limit ?? 50}
                onChange={(e) =>
                  onChange({ pairing_pending_limit: e.target.value ? Number(e.target.value) : undefined })
                }
              />
            </Field>
          </FieldRow>
        </div>
      )}

      {gateway.direct_policy !== 'Disabled' && (
        <div className="space-y-3 rounded-lg border p-4">
          <p className="text-sm font-medium">People</p>
          <AccessTab gateway={gateway.name} />
        </div>
      )}
    </>
  );
}
