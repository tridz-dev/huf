import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, Send } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { getExternalSessionEvents, postExternalUserMessage } from '@/services/externalAgentsApi';
import type { ExternalEvent, ExternalSession } from '@/types/externalAgents.types';

const TRANSCRIPT_POLL_MS = 5_000;
const TERMINAL_STATES: ReadonlyArray<ExternalSession['state']> = ['Completed', 'Failed', 'Cancelled'];

function isTerminalSessionState(state: ExternalSession['state']): boolean {
  return TERMINAL_STATES.includes(state);
}

type Payload = Record<string, unknown>;

interface TimelineItem {
  key: string;
  tone: 'user' | 'agent' | 'neutral';
  kind?: string;
  text: string;
}

function asPayload(value: unknown): Payload {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Payload) : {};
}

function stringField(payload: Payload, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return undefined;
}

function prettify(raw: string): string {
  const spaced = raw.replace(/[_-]+/g, ' ').trim().toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function describeEvent(event: ExternalEvent): TimelineItem {
  const payload = asPayload(event.payload);
  const key = String(event.seq);
  const status = stringField(payload, ['status']) ?? event.status;

  switch (event.event_type) {
    case 'user_message':
      return {
        key,
        tone: 'user',
        text: `You: ${stringField(payload, ['text', 'message', 'content']) ?? ''}`.trimEnd(),
      };
    case 'report':
      return {
        key,
        tone: 'agent',
        kind: stringField(payload, ['kind']) ? prettify(stringField(payload, ['kind']) as string) : undefined,
        text: stringField(payload, ['text', 'message', 'summary', 'content']) ?? '',
      };
    case 'tool_result': {
      const tool = stringField(payload, ['tool', 'tool_name']);
      const statusPart = status ? ` (${status})` : '';
      return {
        key,
        tone: 'neutral',
        text: tool ? `Ran ${tool}${statusPart}` : `Ran a tool${statusPart}`,
      };
    }
    case 'complete':
      return { key, tone: 'neutral', text: 'Finished' };
    case 'approval_decided':
      return { key, tone: 'neutral', text: `Approval ${String(status ?? '').toLowerCase()}`.trimEnd() };
    case 'session_cancelled':
      return { key, tone: 'neutral', text: 'Session cancelled' };
    default:
      return { key, tone: 'neutral', text: prettify(event.event_type) };
  }
}

interface SessionTranscriptDialogProps {
  session: ExternalSession;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SessionTranscriptDialog({ session, open, onOpenChange }: SessionTranscriptDialogProps) {
  const [events, setEvents] = useState<ExternalEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);

  const sessionName = session.name;
  const isTerminal = isTerminalSessionState(session.state);

  const loadEvents = useCallback(async () => {
    try {
      const rows = await getExternalSessionEvents(sessionName, 200);
      setEvents([...rows].sort((a, b) => a.seq - b.seq));
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [sessionName]);

  useEffect(() => {
    if (!open) return;
    setEvents([]);
    setLoading(true);
    void loadEvents();
    const intervalId = window.setInterval(() => void loadEvents(), TRANSCRIPT_POLL_MS);
    return () => window.clearInterval(intervalId);
  }, [open, sessionName, loadEvents]);

  const items = useMemo(() => events.map(describeEvent), [events]);

  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [items.length]);

  const canSend = !isTerminal && !sending && draft.trim().length > 0;

  async function sendMessage() {
    if (!canSend) return;
    const text = draft.trim();
    setSending(true);
    try {
      await postExternalUserMessage(sessionName, text);
      setDraft('');
      await loadEvents();
    } catch (e) {
      toast.error(getFrappeErrorMessage(e));
    } finally {
      setSending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="break-words">{session.agent}</DialogTitle>
          <DialogDescription>{session.state}</DialogDescription>
        </DialogHeader>

        <div className="max-h-[50vh] min-h-[200px] space-y-3 overflow-y-auto rounded-md border bg-muted/30 p-4">
          {items.length === 0 && loading && <p className="text-sm text-muted-foreground">Loading...</p>}
          {items.length === 0 && !loading && loadError && (
            <p className="text-sm text-muted-foreground">We couldn't load this session. Trying again shortly.</p>
          )}
          {items.length === 0 && !loading && !loadError && (
            <p className="text-sm text-muted-foreground">Nothing has happened yet.</p>
          )}
          {items.map((item) => (
            <div
              key={item.key}
              className={
                item.tone === 'user'
                  ? 'ml-auto max-w-[85%] rounded-md bg-primary/10 px-3 py-2'
                  : 'max-w-[85%] space-y-1'
              }
            >
              {item.kind && (
                <p className="text-micro font-medium uppercase tracking-wide text-muted-foreground">
                  {item.kind}
                </p>
              )}
              <p className="whitespace-pre-wrap break-words text-sm text-foreground">{item.text}</p>
            </div>
          ))}
          <div ref={endRef} />
        </div>

        <div className="space-y-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                void sendMessage();
              }
            }}
            placeholder={isTerminal ? 'This session has ended.' : 'Send a message to the agent...'}
            rows={3}
            disabled={isTerminal || sending}
          />
          <div className="flex justify-end">
            <Button onClick={() => void sendMessage()} disabled={!canSend}>
              {sending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
              Send
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
