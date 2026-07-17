import { useEffect, useState } from 'react';
import { ThumbsDown, ThumbsUp } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import {
  createAgentRunFeedback,
  getAgentMessageIdForRun,
  getExistingRunFeedback,
} from '@/services/chatApi';

interface RunFeedbackActionsProps {
  agentRunId: string;
  agent: string;
  conversation?: string;
}

export function RunFeedbackActions({ agentRunId, agent, conversation }: RunFeedbackActionsProps) {
  const [agentMessageId, setAgentMessageId] = useState<string>();
  const [selected, setSelected] = useState<'Thumbs Up' | 'Thumbs Down' | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [commentDialogOpen, setCommentDialogOpen] = useState(false);
  const [commentText, setCommentText] = useState('');

  useEffect(() => {
    let cancelled = false;

    (async () => {
      setLoading(true);
      const messageId = await getAgentMessageIdForRun(agentRunId);
      if (cancelled) return;
      setAgentMessageId(messageId);

      if (messageId) {
        const existing = await getExistingRunFeedback(messageId);
        if (!cancelled && existing) {
          setSelected(existing.feedback);
        }
      }
      if (!cancelled) setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [agentRunId]);

  const submitFeedback = async (feedback: 'Thumbs Up' | 'Thumbs Down', comments?: string) => {
    setSubmitting(true);
    try {
      await createAgentRunFeedback({
        agent,
        feedback,
        comments,
        conversation,
        agent_message: agentMessageId,
      });
      setSelected(feedback);
      toast.success('Thanks for the feedback!');
    } finally {
      setSubmitting(false);
    }
  };

  const handleThumbsDownSubmit = () => {
    const trimmed = commentText.trim();
    if (!trimmed) {
      toast.error('A comment is required when marking a response as not helpful');
      return;
    }
    submitFeedback('Thumbs Down', trimmed);
    setCommentText('');
    setCommentDialogOpen(false);
  };

  if (loading) return null;

  return (
    <>
      <div className="mt-3 flex items-center gap-2 text-muted-foreground">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={cn('h-7 w-7', selected === 'Thumbs Up' && 'text-emerald-600')}
          disabled={submitting}
          onClick={() => submitFeedback('Thumbs Up')}
          aria-label="Mark response helpful"
          aria-pressed={selected === 'Thumbs Up'}
        >
          <ThumbsUp className="h-4 w-4" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={cn('h-7 w-7', selected === 'Thumbs Down' && 'text-destructive')}
          disabled={submitting}
          onClick={() => setCommentDialogOpen(true)}
          aria-label="Mark response not helpful"
          aria-pressed={selected === 'Thumbs Down'}
        >
          <ThumbsDown className="h-4 w-4" />
        </Button>
      </div>

      <AlertDialog open={commentDialogOpen} onOpenChange={setCommentDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>What went wrong?</AlertDialogTitle>
            <AlertDialogDescription>
              Share a brief comment so we can improve this agent&apos;s behavior.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-3">
            <Textarea
              placeholder="Describe what was incorrect, missing, or unhelpful..."
              value={commentText}
              onChange={(event) => setCommentText(event.target.value)}
              className="min-h-[120px]"
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setCommentText('')}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleThumbsDownSubmit}>Submit</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
