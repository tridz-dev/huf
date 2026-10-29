import { useEffect, useState } from 'react';
import { FieldHint } from '../FieldHint';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { MoreOptions } from '../frame/MoreOptions';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '../../ui/select';
import { edgeRoute } from '../../../services/flowSerializer';
import { getModels, getProviders } from '../../../services/providerApi';
import { isChatModel } from '@/lib/chatModel';
import { type ActionFormProps, type Opt, PickerTextarea, Section, str } from './formKit';
import { useFlowContext } from '../../../contexts/FlowContext';

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
  return (
    <Section title={title} hint="Lets an AI model choose the next step. Connect one arrow from this step to each possible next step and name it (for example urgent, routine). The AI reads your question and the data, then picks the arrow whose name fits best.">
      <div>
        <PickerTextarea
          id="router-prompt"
          testId={f('prompt')}
          pickerTestId={`${f('prompt')}-picker`}
          nodeId={nodeId}
          label="How should the AI choose?"
          value={str(cfg.prompt)}
          onChange={(v) => patch({ prompt: v })}
          format={(ref) => `{${ref}}`}
          placeholder="For example: Is this request urgent or routine?"
        />
        <FieldHint testId="flow-hint-router-prompt">Ask a question the path names can answer. The AI also sees the trigger data and the results of earlier steps. Be specific about when each path applies.</FieldHint>
        <Err field="prompt" />
      </div>
      <div className="space-y-2" data-testid={f('options')}>
        <Label size="sm">Paths</Label>
        <FieldHint testId="flow-hint-router-paths">Each path is an arrow to a next step. A short, clear name helps the AI choose well.</FieldHint>
        {out.length === 0 ? <p className="text-xs text-muted-foreground" data-testid="flow-router-no-paths">No paths yet.</p> : null}
        {out.map((e) => (
          <div key={e.id} className="flex items-center gap-2" data-testid={`flow-router-path-${e.target}`}>
            <Input
              className="min-w-0"
              title={typeof e.label === 'string' ? e.label : undefined}
              aria-label={`Label for path to ${labelOf(e.target)}`}
              data-testid={`flow-router-path-label-${e.target}`}
              value={typeof e.label === 'string' ? e.label : ''}
              placeholder="Name this path"
              onChange={(ev) => updateEdges((activeFlow?.edges ?? []).map((x) => (x.id === e.id ? { ...x, label: ev.target.value } : x)))}
            />
            <span className="text-xs text-muted-foreground truncate w-[84px] shrink-0" title={`Goes to ${labelOf(e.target)}`}>
              {'\u2192 '}{labelOf(e.target)}
            </span>
          </div>
        ))}
        <Err field="options" />
      </div>
      {out.length > 0 && (
        <div>
          <Label htmlFor="router-default" size="sm">If nothing matches, go to</Label>
          <Select value={str(cfg.default)} onValueChange={(v) => patch({ default: v })}>
            <SelectTrigger id="router-default" data-testid={f('default')}>
              <SelectValue placeholder="Choose a path..." />
            </SelectTrigger>
            <SelectContent>
              {out.map((e) => (
                <SelectItem key={e.id} value={e.target}>{labelOf(e.target)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <FieldHint testId="flow-hint-router-default">Used when the AI cannot pick a path or its answer fits none of them.</FieldHint>
          <Err field="default" />
        </div>
      )}
      <MoreOptions defaultOpen={Boolean(cfg.model)}>
      <div>
          <Label htmlFor="router-model" size="sm">AI model (optional)</Label>
          <Select value={str(cfg.model) || DEFAULT_MODEL} onValueChange={(v) => patch({ model: v === DEFAULT_MODEL ? undefined : v })}>
            <SelectTrigger id="router-model" data-testid={f('model')}>
              <SelectValue placeholder="Use provider default" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={DEFAULT_MODEL} data-testid="flow-option-router-model-default">Use provider default</SelectItem>
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
          <FieldHint testId="flow-hint-router-model">Leave on the provider default unless you need a specific model. The provider needs a working key.</FieldHint>
        </div>
      </MoreOptions>
    </Section>
  );
}
