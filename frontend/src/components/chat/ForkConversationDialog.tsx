import { useState } from 'react';
import { Files, ListTodo, AlignLeft, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { forkConversation, type ForkMode } from '@/services/chatApi';

interface ForkConversationDialogProps {
  conversationId: string;
  conversationTitle: string;
  agentName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onForked: (conversationId: string, agentName: string) => void;
}

interface ForkOption {
  mode: ForkMode;
  label: string;
  description: string;
  icon: React.ElementType;
}

const FORK_OPTIONS: ForkOption[] = [
  {
    mode: 'full_history',
    label: 'Full chat history',
    description: 'Copy every message into a new conversation.',
    icon: ListTodo,
  },
  {
    mode: 'summary',
    label: 'Fork with summary',
    description: 'Start with a concise summary and the last exchange.',
    icon: AlignLeft,
  },
  {
    mode: 'last_output',
    label: 'Fork with just last output',
    description: 'Carry over only the final assistant message.',
    icon: Files,
  },
];

export function ForkConversationDialog({
  conversationId,
  conversationTitle,
  agentName,
  open,
  onOpenChange,
  onForked,
}: ForkConversationDialogProps) {
  const [busyMode, setBusyMode] = useState<ForkMode | null>(null);

  async function handleFork(mode: ForkMode) {
    setBusyMode(mode);
    try {
      const result = await forkConversation({ conversationId, mode });
      if (result?.success && result.conversation_id) {
        toast.success('Conversation forked', {
          description: result.title || 'The new chat is ready.',
        });
        onForked(result.conversation_id, agentName);
        onOpenChange(false);
      } else {
        toast.error('Could not fork conversation');
      }
    } catch (error) {
      console.error('Fork error:', error);
      toast.error('Failed to fork conversation', {
        description:
          error instanceof Error
            ? error.message
            : 'An unexpected error occurred. Please try again.',
      });
    } finally {
      setBusyMode(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Fork conversation</DialogTitle>
          <DialogDescription>
            Choose how to fork <span className="font-medium">{conversationTitle}</span>.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 py-4">
          {FORK_OPTIONS.map(({ mode, label, description, icon: Icon }) => {
            const isBusy = busyMode === mode;
            const isAnyBusy = busyMode !== null;
            return (
              <Button
                key={mode}
                variant="outline"
                className={cn(
                  'h-auto justify-start gap-3 px-4 py-3 text-left',
                  isBusy && 'opacity-80'
                )}
                disabled={isAnyBusy}
                onClick={() => handleFork(mode)}
              >
                {isBusy ? (
                  <Loader2 className="h-5 w-5 shrink-0 animate-spin" />
                ) : (
                  <Icon className="h-5 w-5 shrink-0" />
                )}
                <div className="flex flex-col gap-0.5">
                  <span className="text-sm font-medium">{label}</span>
                  <span className="text-xs text-muted-foreground leading-snug">
                    {description}
                  </span>
                </div>
              </Button>
            );
          })}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busyMode !== null}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
