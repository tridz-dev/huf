import { useEffect, useState } from 'react';
import { Combobox } from '../../ui/combobox';
import { FieldHint } from '../FieldHint';
import { Label } from '../../ui/label';
import { getAgents } from '../../../services/agentApi';
import { linkRoutes } from '@/lib/link-routes';
import { promptToValue, valueToPrompt } from '@/lib/flow-data/textRefs';
import { type ActionFormProps, type Opt, Section, str } from './formKit';
import { useAsValue } from './useAsValue';
import { ValueField } from './fields';

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

  // The prompt and the data it uses are stored apart; the person sees one box with chips.
  const [prompt, toStored] = useAsValue(
    { prompt: cfg.prompt, prompt_bindings: cfg.prompt_bindings },
    (s) => promptToValue(s.prompt, s.prompt_bindings),
    (v) => valueToPrompt(v)
  );
  return (
    <Section title={title} hint="Asks one of your AI agents to do a task. The agent's reply goes to the next step. A test run asks the agent for real, but nothing it would send or change is done.">
      <div>
        <Label htmlFor="agent-name" size="sm">Which agent</Label>
        <Combobox
          id="agent-name"
          testId={f('agent')}
          options={agents}
          value={str(cfg.agent)}
          onValueChange={(v) => patch({ agent: v })}
          placeholder={loading ? 'Loading...' : 'Choose an agent...'}
          disabled={loading}
          searchPlaceholder="Search agents..."
          emptyText={agents.length ? 'No agent with that name.' : 'No agents are available to your account yet. Create one on the Agents page.'}
          linkTo={linkRoutes.agent}
        />
        <FieldHint testId="flow-hint-agent-run-agent">The AI agent that does the work. You can create or change agents on the Agents page.</FieldHint>
        <Err field="agent" />
      </div>
      <ValueField
        field="prompt"
        f={f}
        Err={Err}
        nodeId={nodeId}
        label="What to tell it"
        kind="longtext"
        placeholder="Summarise this support ticket in two sentences, then suggest a reply."
        hint="Write the task as you would to a colleague. Use + Use data to include details from the trigger or an earlier step, like the ticket text."
        value={prompt}
        onChange={(v) => patch(toStored(v))}
      />
    </Section>
  );
}
