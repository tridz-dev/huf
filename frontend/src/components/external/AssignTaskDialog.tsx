import { useId, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { assignExternalTask } from '@/services/external/agentsApi';

const MAX_TASK_LENGTH = 8000;

interface AssignTaskDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  connection: string;
  agentName: string;
}

export function AssignTaskDialog({ open, onOpenChange, connection, agentName }: AssignTaskDialogProps) {
  const textareaId = useId();
  const [text, setText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const trimmed = text.trim();
  const isTooLong = trimmed.length > MAX_TASK_LENGTH;
  const canSend = trimmed.length > 0 && !isTooLong && !isSubmitting;

  const handleSend = async () => {
    if (!canSend) return;

    setIsSubmitting(true);
    try {
      await assignExternalTask(connection, trimmed);
      toast.success(`Task sent to ${agentName}`);
      onOpenChange(false);
    } catch {
      toast.error("Couldn't send that task. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Send a task to {agentName}</DialogTitle>
          <DialogDescription>Give it something to do on your behalf.</DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor={textareaId}>What should your connected app do?</Label>
          <Textarea
            id={textareaId}
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={6}
            aria-invalid={isTooLong}
          />
          <p className="text-xs text-muted-foreground">
            Your connected app picks this up the next time it checks in. You can follow progress under
            Agent sessions.
          </p>
          {isTooLong && (
            <p className="text-xs text-destructive">
              Tasks can be up to {MAX_TASK_LENGTH.toLocaleString()} characters.
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void handleSend()} disabled={!canSend}>
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Send
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
