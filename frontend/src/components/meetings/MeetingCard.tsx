import { Calendar, Clock } from 'lucide-react';
import { ItemCard } from '@/components/dashboard';
import { formatTimeAgo } from '@/utils/time';
import type { MeetingListItem, MeetingStatus } from '@/types/meeting.types';
import type { BadgeVariant } from '@/utils/status';

interface MeetingCardProps {
  meeting: MeetingListItem;
  onClick: () => void;
}

function statusPresentation(status: MeetingStatus): { label: string; variant: BadgeVariant } {
  switch (status) {
    case 'Recording':
      return { label: 'recording', variant: 'destructive' };
    case 'Paused':
      return { label: 'paused', variant: 'secondary' };
    case 'Stopped':
    case 'Transcribing':
    case 'Summarizing':
      return { label: 'processing', variant: 'outline' };
    case 'Completed':
      return { label: 'completed', variant: 'success' };
    case 'Failed':
      return { label: 'failed', variant: 'destructive' };
    case 'Draft':
    default:
      return { label: 'draft', variant: 'secondary' };
  }
}

/** Short, list-view-appropriate failure reason — the detail page shows the
 * full `last_error`/`error_log`, this is just enough to tell failed
 * meetings apart at a glance without opening each one. */
export function failureReason(meeting: MeetingListItem): string | undefined {
  if (meeting.status !== 'Failed') return undefined;
  if (meeting.failed_step === 'Model Not Configured') return 'No AI model configured';
  if (meeting.last_error) return meeting.last_error.slice(0, 140);
  return 'Failed to process';
}

function formatDuration(seconds?: number): string {
  if (!seconds || seconds <= 0) return '—';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remaining = minutes % 60;
  return remaining > 0 ? `${hours}h ${remaining}m` : `${hours}h`;
}

/** Thin `ItemCard` wrapper for one meeting in the history grid — title (or
 * placeholder), relative date, duration, status pill, and a summary
 * excerpt once available (PLAN.md G.1 "Meeting-history usability"). */
export function MeetingCard({ meeting, onClick }: MeetingCardProps) {
  const status = statusPresentation(meeting.status);
  const title = meeting.title?.trim() || `Meeting — ${formatTimeAgo(meeting.started_at || meeting.modified)}`;

  const description =
    failureReason(meeting) ?? (meeting.summary ? meeting.summary.slice(0, 140) : meeting.description?.slice(0, 140));

  return (
    <ItemCard
      title={title}
      description={description}
      status={status}
      metadata={[
        { label: 'When', value: formatTimeAgo(meeting.started_at || meeting.modified), icon: Calendar },
        { label: 'Duration', value: formatDuration(meeting.duration_seconds), icon: Clock },
      ]}
      onClick={onClick}
    />
  );
}
