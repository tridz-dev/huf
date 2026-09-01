import { useState } from 'react';
import { Link } from 'react-router-dom';
import { BarChart2, RefreshCw, ThumbsDown, ThumbsUp } from 'lucide-react';
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
import { CopyButton } from './CopyButton';

interface MessageActionsProps {
  content: string;
  agentMessageId?: string;
  agentRunId?: string;
  onFeedback: (feedback: 'Thumbs Up' | 'Thumbs Down', options?: { agentMessageId?: string; comments?: string }) => void;
  /** Re-runs the user turn that produced this response. Omitted when the source turn is unknown. */
  onRegenerate?: () => void;
  /** True while a turn is already in flight, to prevent overlapping runs. */
  regenerateDisabled?: boolean;
}

export function MessageActions({ content, agentMessageId, agentRunId, onFeedback, onRegenerate, regenerateDisabled }: MessageActionsProps) {
  const [commentDialogOpen, setCommentDialogOpen] = useState(false);
  const [commentText, setCommentText] = useState('');


  const handleSubmitComment = () => {
    const trimmed = commentText.trim();
    onFeedback('Thumbs Down', { agentMessageId, comments: trimmed || ""});
    setCommentText('');
    setCommentDialogOpen(false);
  };

  return (
    <>
      <div className="mt-3 flex items-center gap-1 text-muted-foreground">
        <CopyButton content={content} />
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="text-steel-soft hover:text-ink"
          onClick={() => onFeedback('Thumbs Up', { agentMessageId })}
          aria-label="Mark response helpful"
        >
          <ThumbsUp className="size-[15px]" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="text-steel-soft hover:text-ink"
          onClick={() => setCommentDialogOpen(true)}
          aria-label="Mark response not helpful"
        >
          <ThumbsDown className="size-[15px]" />
        </Button>
        {onRegenerate && (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="text-steel-soft hover:text-ink"
            onClick={onRegenerate}
            disabled={regenerateDisabled}
            aria-label="Regenerate response"
            title="Regenerate response"
          >
            <RefreshCw className="size-[15px]" />
          </Button>
        )}
        {agentRunId && (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="text-steel-soft hover:text-ink"
            asChild
            aria-label="View context & cache metrics"
          >
            <Link
              to={`/executions/${agentRunId}`}
              target="_blank"
              rel="noopener noreferrer"
              title="View context & cache metrics"
            >
              <BarChart2 className="size-[15px]" />
            </Link>
          </Button>
        )}
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
            <AlertDialogCancel
              onClick={() => {
                setCommentText('');
              }}
            >
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction onClick={handleSubmitComment}>Submit</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

