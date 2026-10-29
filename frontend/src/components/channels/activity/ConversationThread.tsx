import { useEffect, useState } from 'react';
import { ExternalLink, Loader2, SquareAsterisk } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useIsHufAdmin } from '@/contexts/PermissionsContext';
import { TimeStamp } from '@/components/whatsapp/TimeStamp';
import {
  closeConversation,
  getConversation,
  returnToAi,
  type ConversationDetail,
  type ConversationMessage,
  type ConversationToolCall,
} from '@/services/channelsApi';

const slug = (doctype: string) => doctype.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-');
export const deskHref = (doctype: string, name: string) => `/app/${slug(doctype)}/${encodeURIComponent(name)}`;
const APP_LABEL: Record<string, string> = { 'HD Ticket': 'Help Desk', 'CRM Lead': 'CRM', 'CRM Deal': 'CRM' };

export function ConversationThread({ name, onChanged }: { name: string; onChanged?: () => void }) {
  const isAdmin = useIsHufAdmin();
  const [conv, setConv] = useState<ConversationDetail | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [tools, setTools] = useState<ConversationToolCall[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError('');
    void getConversation(name).then((res) => {
      if (!live) return;
      if (res.ok) {
        const d = res.data as { conversation?: ConversationDetail; messages?: ConversationMessage[]; tool_calls?: ConversationToolCall[] };
        setConv(d.conversation ?? (d as unknown as ConversationDetail));
        setMessages(d.messages ?? []);
        setTools(d.tool_calls ?? []);
      } else setError(res.error);
      setLoading(false);
    });
    return () => {
      live = false;
    };
  }, [name]);

  const act = async (fn: typeof returnToAi) => {
    setBusy(true);
    const res = await fn(name);
    setBusy(false);
    if (!res.ok) return setError(res.error);
    const status = res.data.conversation_status as ConversationDetail['status'] | undefined;
    if (status && conv) setConv({ ...conv, status });
    onChanged?.();
  };

  if (loading) return <div className="flex items-center gap-2 p-4 text-xs text-steel"><Loader2 className="h-4 w-4 animate-spin" /> Loading...</div>;
  if (error && !conv) return <p role="alert" className="p-4 text-sm text-destructive">{error}</p>;

  // Tool chips sit after the last message of the run that made them.
  const lastOfRun = new Map<string, number>();
  messages.forEach((m, i) => { if (m.agent_run) lastOfRun.set(m.agent_run, i); });

  return (
    <div className="flex h-full min-h-0 flex-col" data-thread={name}>
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2">
        <span className="flex-1 truncate text-sm font-medium text-ink">{conv?.contact_name || conv?.contact_handle || name}</span>
        {conv?.handoff_doctype && conv.handoff_name && (
          <a
            href={deskHref(conv.handoff_doctype, conv.handoff_name)}
            className="inline-flex items-center gap-1 rounded-full border border-line px-2 py-0.5 font-mono text-[11px] text-ink"
          >
            Open in {APP_LABEL[conv.handoff_doctype] ?? conv.handoff_doctype} <ExternalLink className="h-3 w-3" aria-hidden />
          </a>
        )}
        {isAdmin && (
          <>
            {conv?.status === 'handed_off' && <Button size="sm" variant="outline" disabled={busy} onClick={() => void act(returnToAi)}>Return to AI</Button>}
            {conv?.status !== 'closed' && <Button size="sm" variant="outline" disabled={busy} onClick={() => void act(closeConversation)}>Close</Button>}
          </>
        )}
      </div>
      {error && <p role="alert" className="px-4 py-1 text-xs text-destructive">{error}</p>}
      <div className="flex-1 space-y-2 overflow-y-auto p-4">
        {messages.map((m, i) => {
          const out = m.direction === 'out';
          const ai = out && m.sent_by === 'agent';
          return (
            <div key={`${m.message_id ?? i}-${i}`}>
              <div className={out ? 'flex justify-end' : 'flex justify-start'}>
                <div className={`max-w-[80%] rounded-sm border border-line px-3 py-2 text-sm text-ink ${out ? 'bg-paper-deep' : 'bg-card'}`}>
                  {ai && (
                    <div className="mb-1 flex items-center gap-1 text-[11px] text-steel">
                      <SquareAsterisk className="h-3 w-3" aria-hidden /> {m.agent || 'Agent'}
                    </div>
                  )}
                  <div className="whitespace-pre-wrap break-words">{m.text}</div>
                  <div className="mt-1 text-[11px] text-steel"><TimeStamp value={m.creation} /></div>
                </div>
              </div>
              {m.agent_run && lastOfRun.get(m.agent_run) === i && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {tools.filter((t) => t.agent_run === m.agent_run).map((t) => (
                    <span key={t.name} data-tool-call className="rounded-sm border border-line bg-paper-deep px-1.5 py-0.5 font-mono text-[11px] text-steel">
                      {t.tool} · {t.status}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {conv?.handoff_doctype && conv.handoff_name && (
          <div data-handoff-row className="flex justify-center">
            <Badge variant="pill-warning">Handed off to {APP_LABEL[conv.handoff_doctype] ?? conv.handoff_doctype}: {conv.handoff_name}</Badge>
          </div>
        )}
      </div>
    </div>
  );
}
