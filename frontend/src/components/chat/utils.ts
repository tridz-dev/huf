import { toDate } from "@/utils/time";
import type { ExtendedToolState } from '@/components/ai-elements/types';

export function formatTime(timestamp?: string): string {
    if (!timestamp) return '';
    const date = toDate(timestamp);
    if (!date) return '';
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    return `${hours}:${minutes}`;
}

// Map tool_status to ExtendedToolState
export function mapToolStatusToState(status?: string): ExtendedToolState {
  switch (status) {
    case 'Started':
      return 'input-available';
    case 'Queued':
      return 'input-streaming';
    case 'Completed':
      return 'output-available';
    case 'Failed':
      return 'output-error';
    default:
      return 'input-streaming';
  }
}
