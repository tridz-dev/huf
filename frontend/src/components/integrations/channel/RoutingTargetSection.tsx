import { Field, FieldRow } from '@/components/ui/field';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { GatewayDoc } from '@/services/gatewayApi';

interface RoutingTargetSectionProps {
  gateway: GatewayDoc;
  agents: { name: string; agent_name: string }[];
  flows: { name: string; title: string }[];
  onChange: (patch: Partial<GatewayDoc>) => void;
}

export function RoutingTargetSection({ gateway, agents, flows, onChange }: RoutingTargetSectionProps) {
  return (
    <div className="grid gap-3 rounded-lg border p-4">
      <p className="text-sm font-medium">Routing target</p>
      <FieldRow cols={2}>
        <Field label="Target type" size="sm">
          {(fp) => (
            <Select
              value={gateway.default_target_type || '__none'}
              onValueChange={(v) =>
                onChange({
                  default_target_type: (v === '__none' ? '' : v) as GatewayDoc['default_target_type'],
                })
              }
            >
              <SelectTrigger {...fp}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none">None</SelectItem>
                <SelectItem value="Agent">Agent</SelectItem>
                <SelectItem value="Flow">Flow</SelectItem>
              </SelectContent>
            </Select>
          )}
        </Field>

        {gateway.default_target_type === 'Agent' && (
          <Field label="Agent" size="sm">
            {(fp) => (
              <Select
                value={gateway.default_agent || '__none'}
                onValueChange={(v) => onChange({ default_agent: v === '__none' ? '' : v })}
              >
                <SelectTrigger {...fp}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">Choose an agent…</SelectItem>
                  {agents.map((a) => (
                    <SelectItem key={a.name} value={a.name}>
                      {a.agent_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </Field>
        )}

        {gateway.default_target_type === 'Flow' && (
          <Field label="Flow" size="sm">
            {(fp) => (
              <Select
                value={gateway.default_flow || '__none'}
                onValueChange={(v) => onChange({ default_flow: v === '__none' ? '' : v })}
              >
                <SelectTrigger {...fp}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">Choose a flow…</SelectItem>
                  {flows.map((f) => (
                    <SelectItem key={f.name} value={f.name}>
                      {f.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </Field>
        )}
      </FieldRow>
    </div>
  );
}
