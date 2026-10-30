import { useEffect, useState } from 'react';
import { Button } from '../../ui/button';
import { Combobox } from '../../ui/combobox';
import { FieldHint } from '../FieldHint';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Textarea } from '../../ui/textarea';
import { VariablePicker } from '../../ui/VariablePicker';
import { getAgents } from '../../../services/agentApi';
import { linkRoutes } from '@/lib/link-routes';
import { type ActionFormProps, asObj, type Cfg, type Opt, Section, str } from './formKit';
import { uniqueName } from '@/lib/flow/flowRefs';

export function AgentRunForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const [agents, setAgents] = useState<Opt[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    getAgents()
      .then((r) => {
        const items = Array.isArray(r) ? r : r.items;
        setAgents((items || []).map((a: { name: string; agent_name?: string }) => ({ value: a.name, label: a.agent_name || a.name })));
      })
      .catch(() => setAgents([]))
      .finally(() => setLoading(false));
  }, []);

  const agentPromptPicker = (current: string, bindings: Cfg) => (
    <VariablePicker
      currentNodeId={nodeId}
      testId="flow-agent-run-variable-picker"
      onSelect={(ref, suggested) => {
        const existing = Object.entries(bindings).find(([, v]) => asObj(v).$from === ref)?.[0];
        const name = existing ?? uniqueName(suggested, Object.keys(bindings));
        patch({
          prompt: `${current}${current && !current.endsWith(' ') ? ' ' : ''}{${name}}`,
          prompt_bindings: { ...bindings, [name]: { $from: ref } },
        });
      }}
    />
  );
  const prompt = str(cfg.prompt);
  const bindings = asObj(cfg.prompt_bindings);
  return (
    <Section title={title} hint="Asks one of your AI agents to do a task. The agent's reply goes to the next step.">
      <div>
        <Label htmlFor="agent-name" size="sm">Agent</Label>
        <Combobox
          id="agent-name"
          testId={f('agent')}
          options={agents}
          value={str(cfg.agent)}
          onValueChange={(v) => patch({ agent: v })}
          placeholder={loading ? 'Loading...' : 'Choose an agent...'}
          disabled={loading}
          searchPlaceholder="Search agents..."
          emptyText={agents.length ? 'No matching agent.' : 'No agents are available to your account.'}
          linkTo={linkRoutes.agent}
        />
        <FieldHint testId="flow-hint-agent-run-agent">The agent that does the work. Create or change agents on the Agents page.</FieldHint>
        <Err field="agent" />
      </div>
      <div>
        <div className="flex justify-between items-center mb-1">
          <Label htmlFor="agent-prompt" size="sm">Prompt</Label>
          {agentPromptPicker(prompt, bindings)}
        </div>
        <Textarea
          id="agent-prompt"
          data-testid={f('prompt')}
          className="min-h-[80px] w-full"
          value={prompt}
          onChange={(e) => patch({ prompt: e.target.value })}
          placeholder="Summarise this support ticket in two sentences: {ticket}"
        />
        <FieldHint testId="flow-hint-agent-run-prompt">Write the task as you would to a person. Click + Use data, or type {'{name}'}, to include data from the trigger or an earlier step.</FieldHint>
        <Err field="prompt" />
      </div>
      {Object.keys(bindings).length > 0 && (
        <div className="space-y-2" data-testid={f('prompt_bindings')}>
          <Label size="sm">Data used in the prompt</Label>
          <FieldHint testId="flow-hint-agent-run-bindings">Each {'{name}'} in the prompt is replaced by the data below, for example input.ticket.</FieldHint>
          {Object.entries(bindings).map(([name, value]) => (
            <div key={name} className="space-y-1" data-testid={`flow-binding-${name}`}>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs flex-1 min-w-0 truncate">{`{${name}}`}</span>
                <VariablePicker
                  currentNodeId={nodeId}
                  testId={`flow-binding-picker-${name}`}
                  label={`Pick the data for ${name}`}
                  onSelect={(ref) => patch({ prompt_bindings: { ...bindings, [name]: { $from: ref } } })}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove ${name}`}
                  onClick={() => {
                    const next = { ...bindings };
                    delete next[name];
                    patch({ prompt_bindings: Object.keys(next).length ? next : undefined });
                  }}
                >
                  ×
                </Button>
              </div>
              <Input
                className="font-mono text-xs"
                aria-label={`Source for ${name}`}
                data-testid={`flow-binding-source-${name}`}
                value={str(asObj(value).$from)}
                onChange={(e) => patch({ prompt_bindings: { ...bindings, [name]: { $from: e.target.value } } })}
              />
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}
