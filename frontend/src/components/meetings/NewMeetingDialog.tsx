import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';

interface NewMeetingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onStart: (details: { title?: string; description?: string; participants?: string }) => void;
  starting?: boolean;
}

/**
 * Optional "New meeting with details" form. Every field is optional and
 * skippable — recording never blocks on this dialog (PLAN.md G.1 "Start-
 * recording friction"). Quick Start bypasses this entirely.
 */
export function NewMeetingDialog({ open, onOpenChange, onStart, starting }: NewMeetingDialogProps) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [participants, setParticipants] = useState('');

  const reset = () => {
    setTitle('');
    setDescription('');
    setParticipants('');
  };

  const handleStart = () => {
    onStart({
      title: title.trim() || undefined,
      description: description.trim() || undefined,
      participants: participants.trim() || undefined,
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New meeting</DialogTitle>
          <DialogDescription>
            All fields are optional — you can add or edit these after the meeting too.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="new-meeting-title">Title</Label>
            <Input
              id="new-meeting-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="e.g. Weekly product sync"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-meeting-description">Description</Label>
            <Textarea
              id="new-meeting-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What is this meeting about?"
              rows={3}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-meeting-participants">Participants</Label>
            <Input
              id="new-meeting-participants"
              value={participants}
              onChange={(event) => setParticipants(event.target.value)}
              placeholder="Names or emails, comma separated"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={starting}>
              Cancel
            </Button>
            <Button type="button" variant="display" onClick={handleStart} disabled={starting}>
              {starting ? 'Starting...' : 'Start recording'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
