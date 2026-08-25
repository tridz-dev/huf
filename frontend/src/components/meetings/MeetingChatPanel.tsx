import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { AlertTriangle, MessageSquare, Send, Sparkles } from 'lucide-react';
import { Streamdown } from 'streamdown';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { askMeeting, getChatHistory, reviseSummary } from '@/services/meetingChat';
import type { MeetingChatMessage } from '@/types/meeting.types';

interface MeetingChatPanelProps {
  meetingName: string;
  hasTranscript: boolean;
  hasSummary: boolean;
  onSummaryRevised: () => void;
}

/**
 * Tiny, minimal "chat with the meeting" panel — a lightweight alternative
 * to Firefly's Q&A/rewrite features, not a full chat product. Two actions:
 * ask a question about the transcript, and revise the summary with a
 * one-off instruction. Both are logged server-side as `Meeting Chat
 * Message` docs (visible in logs per the task requirement) and this panel
 * simply re-fetches that history after each send rather than doing
 * optimistic updates.
 */
export function MeetingChatPanel({ meetingName, hasTranscript, hasSummary, onSummaryRevised }: MeetingChatPanelProps) {
  const [history, setHistory] = useState<MeetingChatMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [question, setQuestion] = useState('');
  const [asking, setAsking] = useState(false);
  const [instruction, setInstruction] = useState('');
  const [revising, setRevising] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    if (!hasTranscript) {
      setLoadingHistory(false);
      return;
    }
    (async () => {
      try {
        const rows = await getChatHistory(meetingName);
        if (!cancelled) setHistory(rows);
      } catch {
        // getMeeting/other panels already surface load failures; keep this
        // panel quiet on initial history load and just show an empty log.
      } finally {
        if (!cancelled) setLoadingHistory(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [meetingName, hasTranscript]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [history.length]);

  const refreshHistory = async () => {
    try {
      const rows = await getChatHistory(meetingName);
      setHistory(rows);
    } catch (err) {
      toast.error('Failed to refresh chat history', {
        description: err instanceof Error ? err.message : 'An unexpected error occurred.',
      });
    }
  };

  const handleAsk = async () => {
    const message = question.trim();
    if (!message || asking) return;
    setAsking(true);
    setQuestion('');
    try {
      await askMeeting(meetingName, message);
      await refreshHistory();
    } catch (err) {
      toast.error('Failed to send message', {
        description: err instanceof Error ? err.message : 'An unexpected error occurred.',
      });
    } finally {
      setAsking(false);
    }
  };

  const handleRevise = async () => {
    const text = instruction.trim();
    if (!text || revising) return;
    setRevising(true);
    try {
      const result = await reviseSummary(meetingName, text);
      if (result.error) {
        toast.error('Could not revise summary', { description: result.error });
      } else {
        setInstruction('');
        toast.success('Summary revised');
        onSummaryRevised();
      }
    } catch (err) {
      toast.error('Failed to revise summary', {
        description: err instanceof Error ? err.message : 'An unexpected error occurred.',
      });
    } finally {
      setRevising(false);
    }
  };

  if (!hasTranscript) {
    return (
      <Card>
        <CardHeader className="flex flex-row items-center gap-2 space-y-0">
          <MessageSquare className="h-4 w-4 text-steel-soft" aria-hidden />
          <CardTitle className="text-sm">Ask this meeting</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="font-body text-sm text-steel">Chat is available once a transcript exists.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2 space-y-0">
        <MessageSquare className="h-4 w-4 text-steel-soft" aria-hidden />
        <CardTitle className="text-sm">Ask this meeting</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div
          className="flex max-h-[40vh] min-h-[80px] flex-col gap-3 overflow-y-auto rounded-lg border border-line p-3"
          role="log"
          aria-label="Meeting chat"
        >
          {loadingHistory ? (
            <p className="font-body text-xs text-steel-soft">Loading chat...</p>
          ) : history.length === 0 ? (
            <p className="font-body text-xs text-steel-soft">
              Ask a question about this meeting — e.g. "What did we decide about the launch date?"
            </p>
          ) : (
            history.map((msg) => (
              <div key={msg.name} className={cn('flex flex-col gap-1', msg.role === 'user' ? 'items-end' : 'items-start')}>
                <span className="font-body text-[10px] font-medium uppercase tracking-wide text-steel-soft">
                  {msg.role === 'user' ? 'You' : 'Assistant'}
                </span>
                {msg.error ? (
                  <p className="flex max-w-[85%] items-start gap-1.5 rounded-lg border border-signal-ink/40 bg-transparent px-3 py-2 text-sm text-signal-ink">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                    {msg.error}
                  </p>
                ) : (
                  <div
                    className={cn(
                      'max-w-[85%] rounded-lg px-3 py-2 text-sm prose prose-sm [&_p]:my-0',
                      msg.role === 'user' ? 'bg-paper-deep text-ink' : 'border border-line text-ink',
                    )}
                  >
                    <Streamdown>{msg.content}</Streamdown>
                  </div>
                )}
                {!!msg.applied_to_summary && (
                  <Badge variant="pill-success" size="sm">Applied to summary</Badge>
                )}
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>

        <div className="flex items-center gap-2">
          <Input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleAsk();
              }
            }}
            placeholder="Ask a question about this meeting..."
            disabled={asking}
          />
          <Button size="sm" onClick={handleAsk} disabled={asking || !question.trim()}>
            <Send className="h-3.5 w-3.5" aria-hidden />
          </Button>
        </div>

        <div className="flex flex-col gap-2 border-t border-line pt-4">
          <div className="flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-steel-soft" aria-hidden />
            <span className="font-body text-xs font-medium text-ink">Revise summary with a prompt</span>
          </div>
          <Textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder={hasSummary ? 'e.g. "Make the action items more concise"' : 'Meeting has no summary yet.'}
            disabled={revising || !hasSummary}
            className="min-h-[52px] text-sm"
          />
          <Button
            variant="outline"
            size="sm"
            className="self-start"
            onClick={handleRevise}
            disabled={revising || !hasSummary || !instruction.trim()}
          >
            {revising ? 'Revising...' : 'Revise summary'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
