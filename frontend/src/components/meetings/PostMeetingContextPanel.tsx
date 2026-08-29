import { useState } from 'react';
import { X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { updateMeetingContext } from '@/services/meetingApi';

interface PostMeetingContextPanelProps {
  meetingName: string;
  onDismiss: () => void;
  onSaved: (values: { title?: string; description?: string; participants?: string }) => void;
}

/**
 * Non-modal, dismissible inline prompt shown once per meeting right after
 * Stop (PLAN.md G.1 "post-meeting context" / L Phase 7): three optional
 * fields, "Skip" is as prominent as "Save" since none of this blocks
 * processing — it only improves the summary prompt (meeting_summary.py
 * _build_summary_prompt reads title/description/participants when present).
 */
export function PostMeetingContextPanel({ meetingName, onDismiss, onSaved }: PostMeetingContextPanelProps) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [participants, setParticipants] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await updateMeetingContext({
        meetingName,
        title: title.trim() || undefined,
        description: description.trim() || undefined,
        participants: participants.trim() || undefined,
      });
      toast.success('Meeting details saved');
      onSaved({
        title: result.title,
        description: result.description,
        participants: result.participants,
      });
    } catch (error) {
      toast.error('Could not save meeting details', {
        description: error instanceof Error ? error.message : 'An unexpected error occurred.',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="relative rounded-lg border border-line bg-card p-5" role="region" aria-label="Add meeting context">
      <Button
        variant="ghost"
        size="icon-sm"
        className="absolute right-3 top-3"
        aria-label="Dismiss"
        onClick={onDismiss}
      >
        <X className="h-4 w-4" aria-hidden />
      </Button>

      <h3 className="font-body text-sm font-medium text-ink">Add a title and participants to improve your summary</h3>
      <p className="mt-1 font-body text-[13px] text-steel">Entirely optional — this only helps the summary, it won't delay processing.</p>

      <div className="mt-4 flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="meeting-context-title">Title</Label>
          <Input
            id="meeting-context-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="e.g. Q3 roadmap review"
            disabled={saving}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="meeting-context-participants">Participants</Label>
          <Input
            id="meeting-context-participants"
            value={participants}
            onChange={(event) => setParticipants(event.target.value)}
            placeholder="e.g. Priya, Jordan, Sam"
            disabled={saving}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="meeting-context-description">Description</Label>
          <Textarea
            id="meeting-context-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="What was this meeting about?"
            rows={2}
            disabled={saving}
          />
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </Button>
        <Button variant="outline" size="sm" onClick={onDismiss} disabled={saving}>
          Skip
        </Button>
      </div>
    </div>
  );
}
