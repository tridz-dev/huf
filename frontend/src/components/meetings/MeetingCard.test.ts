// @vitest-environment jsdom
// MeetingCard transitively imports @/components/dashboard -> ActiveAgentsTab
// -> agentApi -> frappe-sdk.ts, which reads window.location at module scope
// (same gotcha as wave-1's useMeetingRecorder.test.ts) — jsdom sidesteps it
// without needing to mock the whole import chain for a pure-function test.
import { describe, it, expect } from 'vitest';
import { failureReason } from './MeetingCard';
import type { MeetingListItem } from '@/types/meeting.types';

function makeMeeting(overrides: Partial<MeetingListItem> = {}): MeetingListItem {
  return {
    name: 'MEETING-001',
    status: 'Completed',
    ...overrides,
  };
}

describe('failureReason', () => {
  it('returns undefined for a non-failed meeting', () => {
    expect(failureReason(makeMeeting({ status: 'Completed' }))).toBeUndefined();
    expect(failureReason(makeMeeting({ status: 'Recording' }))).toBeUndefined();
  });

  it('surfaces a distinct message when the model is not configured', () => {
    expect(
      failureReason(makeMeeting({ status: 'Failed', failed_step: 'Model Not Configured' })),
    ).toBe('No AI model configured');
  });

  it('falls back to a truncated last_error for other failure steps', () => {
    const longError = 'x'.repeat(200);
    expect(failureReason(makeMeeting({ status: 'Failed', failed_step: 'Summary', last_error: longError }))).toBe(
      longError.slice(0, 140),
    );
  });

  it('falls back to a generic message when there is no last_error', () => {
    expect(failureReason(makeMeeting({ status: 'Failed', failed_step: 'Transcription' }))).toBe(
      'Failed to process',
    );
  });
});
