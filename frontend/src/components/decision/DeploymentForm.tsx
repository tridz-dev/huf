import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { call } from '@/lib/frappe-sdk';

/**
 * Editable Decision Deployment settings, laid out like ModelsPage's configure dialog
 * (label + helper text + control, sections separated by a top border). Used by the
 * Decision tab's configure dialog; the dialog shell itself lives in DecisionModelsPage.
 */
export interface DeploymentFormData {
  deployment_name: string;
  enabled: boolean;
  is_default_for_model: boolean;
  priority: string;
  wire_protocol: string;
  endpoint_path: string;
  latency_budget_ms: string;
  supports_select: boolean;
  supports_judge: boolean;
  supports_score: boolean;
  supports_parallel_questions: boolean;
  supports_probabilities: boolean;
  supports_confidence: boolean;
  input_price_per_million: string;
  output_price_per_million: string;
  pricing_override: string;
  provider_rate_limits_json: string;
}

export const emptyDeploymentFormData: DeploymentFormData = {
  deployment_name: '',
  enabled: false,
  is_default_for_model: false,
  priority: '',
  wire_protocol: 'systemone',
  endpoint_path: '',
  latency_budget_ms: '',
  supports_select: false,
  supports_judge: false,
  supports_score: false,
  supports_parallel_questions: false,
  supports_probabilities: false,
  supports_confidence: false,
  input_price_per_million: '',
  output_price_per_million: '',
  pricing_override: '',
  provider_rate_limits_json: '',
};

/** Options mirror the Decision Deployment DocType's `wire_protocol` Select. */
const WIRE_PROTOCOLS = [
  { value: 'systemone', label: 'System One' },
  { value: 'openai_chat_json', label: 'OpenAI chat (JSON)' },
];

const SUPPORT_FLAGS: Array<{ key: keyof DeploymentFormData; label: string; help: string }> = [
  { key: 'supports_select', label: 'Select', help: 'Pick one option from a closed set.' },
  { key: 'supports_judge', label: 'Judge', help: 'Yes/no judgements against criteria.' },
  { key: 'supports_score', label: 'Score', help: 'Score against rubric levels.' },
  { key: 'supports_parallel_questions', label: 'Parallel questions', help: 'Several questions in one call.' },
  { key: 'supports_probabilities', label: 'Probabilities', help: 'Returns per-option probabilities.' },
  { key: 'supports_confidence', label: 'Confidence', help: 'Returns a confidence value.' },
];

type Doc = Record<string, unknown>;

const str = (v: unknown) => (v == null ? '' : String(v));
const num = (v: string) => (v.trim() === '' ? null : Number(v));

export function deploymentDocToForm(doc: Doc): DeploymentFormData {
  return {
    deployment_name: str(doc.deployment_name),
    enabled: doc.enabled === 1,
    is_default_for_model: doc.is_default_for_model === 1,
    priority: str(doc.priority),
    wire_protocol: str(doc.wire_protocol) || 'systemone',
    endpoint_path: str(doc.endpoint_path),
    latency_budget_ms: str(doc.latency_budget_ms),
    supports_select: doc.supports_select === 1,
    supports_judge: doc.supports_judge === 1,
    supports_score: doc.supports_score === 1,
    supports_parallel_questions: doc.supports_parallel_questions === 1,
    supports_probabilities: doc.supports_probabilities === 1,
    supports_confidence: doc.supports_confidence === 1,
    input_price_per_million: str(doc.input_price_per_million),
    output_price_per_million: str(doc.output_price_per_million),
    pricing_override: str(doc.pricing_override),
    provider_rate_limits_json: str(doc.provider_rate_limits_json),
  };
}

/** Returns an error message for the first invalid JSON field, or null. */
export function validateDeploymentForm(data: DeploymentFormData): string | null {
  if (!data.deployment_name.trim()) return 'Deployment name is required';
  for (const [key, label] of [
    ['pricing_override', 'Pricing override'],
    ['provider_rate_limits_json', 'Rate limits'],
  ] as const) {
    const raw = data[key].trim();
    if (!raw) continue;
    try {
      JSON.parse(raw);
    } catch {
      return `${label} must be valid JSON`;
    }
  }
  return null;
}

export function deploymentFormToPayload(data: DeploymentFormData): Doc {
  const flag = (b: boolean) => (b ? 1 : 0);
  return {
    deployment_name: data.deployment_name.trim(),
    enabled: flag(data.enabled),
    is_default_for_model: flag(data.is_default_for_model),
    priority: num(data.priority) ?? 0,
    wire_protocol: data.wire_protocol,
    endpoint_path: data.endpoint_path.trim() || null,
    latency_budget_ms: num(data.latency_budget_ms),
    supports_select: flag(data.supports_select),
    supports_judge: flag(data.supports_judge),
    supports_score: flag(data.supports_score),
    supports_parallel_questions: flag(data.supports_parallel_questions),
    supports_probabilities: flag(data.supports_probabilities),
    supports_confidence: flag(data.supports_confidence),
    input_price_per_million: num(data.input_price_per_million),
    output_price_per_million: num(data.output_price_per_million),
    pricing_override: data.pricing_override.trim() || null,
    provider_rate_limits_json: data.provider_rate_limits_json.trim() || null,
  };
}

export async function getDeploymentDoc(name: string): Promise<Doc> {
  const res = await call.get('frappe.client.get', { doctype: 'Decision Deployment', name });
  return (res.message || {}) as Doc;
}

export async function saveDeployment(name: string, data: DeploymentFormData): Promise<void> {
  await call.post('frappe.client.set_value', {
    doctype: 'Decision Deployment',
    name,
    fieldname: deploymentFormToPayload(data),
  });
}

interface DeploymentFieldsProps {
  value: DeploymentFormData;
  onChange: (next: DeploymentFormData) => void;
}

export function DeploymentFields({ value, onChange }: DeploymentFieldsProps) {
  const set = <K extends keyof DeploymentFormData>(key: K, v: DeploymentFormData[K]) =>
    onChange({ ...value, [key]: v });

  return (
    <div className="space-y-4 py-4">
      <div className="space-y-2">
        <Label htmlFor="deployment_name">
          Deployment Name <span className="text-destructive">*</span>
        </Label>
        <Input
          id="deployment_name"
          value={value.deployment_name}
          onChange={(e) => set('deployment_name', e.target.value)}
        />
      </div>

      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label htmlFor="dep_enabled">Enabled</Label>
          <p className="text-xs text-steel-soft">Disabled deployments are skipped by the failover chain.</p>
        </div>
        <Switch id="dep_enabled" checked={value.enabled} onCheckedChange={(c) => set('enabled', c)} />
      </div>

      <div className="border-t pt-4 space-y-4">
        <div>
          <Label>Failover order</Label>
          <p className="text-xs text-steel-soft mt-0.5">
            The default deployment is tried first, then the rest by ascending priority.
          </p>
        </div>
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label htmlFor="dep_default">Default for this model</Label>
            <p className="text-xs text-steel-soft">Making this the default clears it on the others.</p>
          </div>
          <Switch
            id="dep_default"
            checked={value.is_default_for_model}
            onCheckedChange={(c) => set('is_default_for_model', c)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="dep_priority">Priority</Label>
          <Input
            id="dep_priority"
            type="number"
            placeholder="e.g. 10"
            value={value.priority}
            onChange={(e) => set('priority', e.target.value)}
          />
          <p className="text-xs text-steel-soft">Lower numbers are tried first.</p>
        </div>
      </div>

      <div className="border-t pt-4 space-y-4">
        <Label>Connection</Label>
        <div className="space-y-2">
          <Label htmlFor="dep_wire_protocol">Wire Protocol</Label>
          <Select value={value.wire_protocol} onValueChange={(v) => set('wire_protocol', v)}>
            <SelectTrigger id="dep_wire_protocol">
              <SelectValue placeholder="Select protocol" />
            </SelectTrigger>
            <SelectContent>
              {WIRE_PROTOCOLS.map((p) => (
                <SelectItem key={p.value} value={p.value}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="dep_endpoint_path">Endpoint Path</Label>
          <Input
            id="dep_endpoint_path"
            placeholder="/v1/systemone"
            value={value.endpoint_path}
            onChange={(e) => set('endpoint_path', e.target.value)}
          />
          <p className="text-xs text-steel-soft">Appended to the provider&apos;s base URL.</p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="dep_latency">Latency budget (ms)</Label>
          <Input
            id="dep_latency"
            type="number"
            min="0"
            placeholder="Optional"
            value={value.latency_budget_ms}
            onChange={(e) => set('latency_budget_ms', e.target.value)}
          />
        </div>
      </div>

      <div className="border-t pt-4 space-y-4">
        <div>
          <Label>Capabilities</Label>
          <p className="text-xs text-steel-soft mt-0.5">
            Question kinds and outputs this deployment supports.
          </p>
        </div>
        {SUPPORT_FLAGS.map((f) => (
          <div key={f.key} className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label htmlFor={`dep_${f.key}`}>{f.label}</Label>
              <p className="text-xs text-steel-soft">{f.help}</p>
            </div>
            <Switch
              id={`dep_${f.key}`}
              checked={value[f.key] as boolean}
              onCheckedChange={(c) => set(f.key, c as never)}
            />
          </div>
        ))}
      </div>

      <div className="border-t pt-4 space-y-4">
        <div>
          <Label>Pricing &amp; rate limits</Label>
          <p className="text-xs text-steel-soft mt-0.5">
            Overrides for this deployment. Prices are USD per 1 million tokens.
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="dep_in_price">Input price per 1M tokens</Label>
          <Input
            id="dep_in_price"
            type="number"
            min="0"
            step="0.00000001"
            placeholder="Optional"
            value={value.input_price_per_million}
            onChange={(e) => set('input_price_per_million', e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="dep_out_price">Output price per 1M tokens</Label>
          <Input
            id="dep_out_price"
            type="number"
            min="0"
            step="0.00000001"
            placeholder="Optional"
            value={value.output_price_per_million}
            onChange={(e) => set('output_price_per_million', e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="dep_pricing_override">Pricing override (JSON)</Label>
          <Textarea
            id="dep_pricing_override"
            className="font-mono text-xs"
            rows={3}
            placeholder="Optional"
            value={value.pricing_override}
            onChange={(e) => set('pricing_override', e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="dep_rate_limits">Provider rate limits (JSON)</Label>
          <Textarea
            id="dep_rate_limits"
            className="font-mono text-xs"
            rows={3}
            placeholder="Optional"
            value={value.provider_rate_limits_json}
            onChange={(e) => set('provider_rate_limits_json', e.target.value)}
          />
        </div>
      </div>
    </div>
  );
}
