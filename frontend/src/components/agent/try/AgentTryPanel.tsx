/**
 * AgentTryPanel: TryPanel wired to run_agent_draft_test. Works with unsaved
 * edits (getDraftOverrides). Disabled with an explanation until the agent exists.
 */
import { useRef, useState, type ReactNode } from 'react';
import { TryPanel, TemplateChips, type InspectorItem, type TryMessage } from '@/components/builder';
import { Button } from '@/components/ui/button';
import { isEndpointUnavailable, runAgentDraftTest, type DraftOverrides } from '@/services/agentForm/agentFormApi';

export interface AgentTryPanelProps {
  agentName: string | undefined;
  getDraftOverrides: () => DraftOverrides;
  starters?: string[];
  /** Coaching banner slot; receives the last reply's tool-call names. */
  renderBanner?: (last: { toolNames: string[]; response: string | null } | null) => ReactNode;
  /** Footer model line, e.g. "Model: Gemini Flash (recommended)". */
  modelLabel?: string;
  badge?: string;
}

const secs = (ms: number) => `${(ms / 1000).toFixed(1)}s`;

export function AgentTryPanel({ agentName, getDraftOverrides, starters = [], renderBanner, modelLabel, badge = 'Draft · not published' }: AgentTryPanelProps) {
  const [messages, setMessages] = useState<TryMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [runId, setRunId] = useState<string>();
  const [last, setLast] = useState<{ toolNames: string[]; response: string | null } | null>(null);
  const seq = useRef(0);

  if (!agentName) {
    return (
      <div data-testid="try-disabled" className="flex min-h-96 flex-col items-center justify-center rounded-lg border border-line bg-panel p-6 text-center">
        <h2 className="text-ui-text font-semibold text-ink">Try it</h2>
        <p className="mt-1 max-w-xs text-ui-text text-steel">Create the agent first, then you can test it here with your latest edits, before publishing.</p>
      </div>
    );
  }

  const send = async (text = draft) => {
    const prompt = text.trim();
    if (!prompt || busy) return;
    const id = ++seq.current;
    setDraft('');
    setBusy(true);
    setMessages((m) => [...m, { id: `u${id}`, from: 'user', content: prompt }, { id: `r${id}`, from: 'reply', pending: true, content: 'Thinking…' }]);
    const settle = (patch: Partial<TryMessage>) =>
      setMessages((m) => m.map((x) => (x.id === `r${id}` ? { ...x, pending: false, ...patch } : x)));
    try {
      const r = await runAgentDraftTest(agentName, prompt, getDraftOverrides());
      const inspector: InspectorItem[] = [
        ...r.tool_calls.map((c) => ({ kind: 'call' as const, label: c.tool, detail: c.error_message ?? undefined, failed: c.status === 'Failed' || !!c.error_message })),
        { kind: 'metric', label: secs(r.latency_ms) },
        ...(r.tokens?.total ? [{ kind: 'metric' as const, label: `${r.tokens.total} tokens` }] : []),
      ];
      setRunId(r.agent_run_id);
      setLast({ toolNames: r.tool_calls.map((c) => c.tool), response: r.response });
      settle({ content: r.success ? (r.response ?? '') : (r.error || 'That run did not finish. Check the details.'), inspector });
    } catch (e) {
      settle({
        content: isEndpointUnavailable(e)
          ? 'Testing unsaved edits needs a backend update. Save your changes and use the chat to test for now.'
          : 'Could not run the test. Try again.',
        inspector: [{ kind: 'call', label: 'Failed', failed: true }],
      });
    } finally {
      setBusy(false);
    }
  };

  const reset = () => { setMessages([]); setRunId(undefined); setLast(null); setDraft(''); };

  return (
    <TryPanel badge={badge} onReset={reset} messages={messages} draft={draft} onDraftChange={setDraft}
      onSend={() => void send()} busy={busy} banner={renderBanner?.(last)}
      empty={starters.length > 0 ? <TemplateChips label="Suggestions" items={starters.map((s) => ({ id: s, label: s }))} onPick={(s) => void send(s)} /> : undefined}
      footer={<>
        <span>{modelLabel}</span>
        {runId && <Button asChild variant="link" size="sm"><a href={`/executions/${runId}`}>View run details</a></Button>}
      </>} />
  );
}
