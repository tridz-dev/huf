import { useEffect, useState } from 'react';
import { FieldHint } from '../FieldHint';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { MoreOptions } from '../frame/MoreOptions';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '../../ui/select';
import { edgeRoute } from '../../../services/flowSerializer';
import { getModels, getProviders } from '../../../services/providerApi';
import { isChatModel } from '@/lib/chatModel';
import { type ActionFormProps, type Opt, Section, str } from './formKit';
import { useFlowContext } from '../../../contexts/FlowContext';
import { fromTextRefs, toTextRefs } from '@/lib/flow-data/textRefs';
import { useAsValue } from './useAsValue';
import { ValueField } from './fields';

const DEFAULT_MODEL = '__provider_default__';

export function RouterForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const { activeFlow, updateEdges } = useFlowContext();
  const [modelGroups, setModelGroups] = useState<Array<{ provider: string; models: Opt[] }>>([]);

  useEffect(() => {
    Promise.all([getModels(), getProviders()])
      .then(([models, providers]) => {
        const names = new Map((providers as Array<{ name: string; provider_name?: string }>).map((p) => [p.name, p.provider_name || p.name]));
        const groups = new Map<string, Opt[]>();
        for (const m of models.filter(isChatModel)) {
          const g = names.get(m.provider) ?? m.provider;
          groups.set(g, [...(groups.get(g) ?? []), { value: m.name, label: m.model_name || m.name }]);
        }
        setModelGroups([...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([provider, list]) => ({ provider, models: list })));
      })
      .catch(() => setModelGroups([]));
  }, []);
  const out = (activeFlow?.edges ?? []).filter((e) => e.source === nodeId && edgeRoute(e) === 'option');
  const labelOf = (id: string) => activeFlow?.nodes.find((n) => n.id === id)?.data.label ?? id;
  const [question, toQuestion] = useAsValue(str(cfg.prompt), toTextRefs, (v) => fromTextRefs(v) ?? '');
  const unnamed = out.filter((e) => !(typeof e.label === 'string' && e.label.trim() !== '')).length;
  return (
    <Section title={title} hint="Lets an AI model choose the next step. Name each path with a short word (like urgent or routine). The AI reads your question and the data, then follows the path whose name fits best.">
      <ValueField
        field="prompt"
        f={f}
        Err={Err}
        nodeId={nodeId}
        label="What should the AI decide?"
        kind="longtext"
        placeholder="Is this request urgent or routine?"
        hint="Ask a question that your path names answer, for example: Is this request urgent or routine? The AI also sees the data from the trigger and the steps before. Add details with + Use data, and say when each path applies."
        value={question}
        onChange={(v) => patch({ prompt: toQuestion(v) })}
      />
      <div className="space-y-2" data-testid={f('options')}>
        <Label size="sm">Paths the AI can take</Label>
        <FieldHint testId="flow-hint-router-paths">Each path leads to a next step. Give it a short, clear name: the AI picks the name that fits best.</FieldHint>
        {out.length === 0 ? <p className="text-xs text-muted-foreground" data-testid="flow-router-no-paths">No paths yet. Add a step from this one to make a path.</p> : null}
        {out.map((e) => (
          <div key={e.id} className="rounded-md border border-border p-2 space-y-1" data-testid={`flow-router-path-${e.target}`}>
            <Input
              className="min-w-0"
              title={typeof e.label === 'string' ? e.label : undefined}
              aria-label={`Name of the path to ${labelOf(e.target)}`}
              data-testid={`flow-router-path-label-${e.target}`}
              value={typeof e.label === 'string' ? e.label : ''}
              placeholder="Name this path, for example urgent"
              onChange={(ev) => updateEdges((activeFlow?.edges ?? []).map((x) => (x.id === e.id ? { ...x, label: ev.target.value } : x)))}
            />
            <p className="text-meta text-muted-foreground break-words" data-testid={`flow-router-path-goes-${e.target}`}>
              then goes to <span className="font-medium text-foreground">{labelOf(e.target)}</span>
            </p>
          </div>
        ))}
        {unnamed > 0 && <p className="text-meta text-muted-foreground" data-testid="flow-router-unnamed">A path with no name can only be chosen by its step name.</p>}
        <Err field="options" />
      </div>
      {out.length > 0 && (
        <div>
          <Label htmlFor="router-default" size="sm">If nothing fits, go to</Label>
          <Select value={str(cfg.default)} onValueChange={(v) => patch({ default: v })}>
            <SelectTrigger id="router-default" data-testid={f('default')}>
              <SelectValue placeholder="Choose a path..." />
            </SelectTrigger>
            <SelectContent>
              {out.map((e) => (
                <SelectItem key={e.id} value={e.target}>{typeof e.label === 'string' && e.label.trim() ? `${e.label}: ${labelOf(e.target)}` : labelOf(e.target)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FieldHint testId="flow-hint-router-default">Used when the AI cannot pick a path, or its answer fits none of them.</FieldHint>
          <Err field="default" />
        </div>
      )}
      <MoreOptions defaultOpen={Boolean(cfg.model)}>
        <div>
          <Label htmlFor="router-model" size="sm">AI model (optional)</Label>
          <Select value={str(cfg.model) || DEFAULT_MODEL} onValueChange={(v) => patch({ model: v === DEFAULT_MODEL ? undefined : v })}>
            <SelectTrigger id="router-model" data-testid={f('model')}>
              <SelectValue placeholder="Use the usual model" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={DEFAULT_MODEL} data-testid="flow-option-router-model-default">Use the usual model</SelectItem>
              {modelGroups.map((g) => (
                <SelectGroup key={g.provider}>
                  <SelectLabel>{g.provider}</SelectLabel>
                  {g.models.map((m) => (
                    <SelectItem key={m.value} value={m.value} data-testid={`flow-option-router-model-${m.value}`}>{m.label}</SelectItem>
                  ))}
                </SelectGroup>
              ))}
            </SelectContent>
          </Select>
          <FieldHint testId="flow-hint-router-model">Pick a model only if you need a specific one. The company that provides it needs a working key.</FieldHint>
        </div>
      </MoreOptions>
    </Section>
  );
}
