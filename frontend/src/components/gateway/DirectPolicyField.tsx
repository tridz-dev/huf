import { Field } from '@/components/ui/field';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { GatewayPolicy } from '@/services/gatewayApi';
import { OPEN_POLICY_HELPER_TEXT, directPolicyOptions } from './directPolicy';

const DIRECT_POLICY_LABELS: Record<GatewayPolicy, string> = {
  Open: 'Open — people connect their own account first',
  'Allow list': 'Allow list — Require approved Gateway Access Entry',
  Pairing: 'Pairing — require pairing request approval',
  Disabled: 'Disabled — reject direct messages',
};

interface DirectPolicyFieldProps {
  provider?: string | null;
  value?: GatewayPolicy | null;
  onChange: (value: GatewayPolicy) => void;
}

/** Provider-aware direct message policy select (+ helper text when Open is offered). */
export function DirectPolicyField({ provider, value, onChange }: DirectPolicyFieldProps) {
  const options = directPolicyOptions(provider);
  return (
    <>
      <Field label="Direct message security policy">
        {({ id }) => (
          <Select value={value || 'Allow list'} onValueChange={(v) => onChange(v as GatewayPolicy)}>
            <SelectTrigger id={id}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {options.map((v) => (
                <SelectItem key={v} value={v}>
                  {DIRECT_POLICY_LABELS[v]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </Field>
      {options.includes('Open') && <p className="text-xs text-steel">{OPEN_POLICY_HELPER_TEXT}</p>}
    </>
  );
}
