// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { MeetingRecordingPlayer } from './MeetingRecordingPlayer';
import type { MeetingRecordingChunk } from '@/types/meeting.types';

function makeChunk(overrides: Partial<MeetingRecordingChunk> = {}): MeetingRecordingChunk {
  return {
    name: 'chunk-1',
    sequence: 0,
    audio_file: '/private/files/fake-recording.webm',
    upload_status: 'Transcribed',
    duration_seconds: 6,
    transcript_text: 'Alice said we should ship it',
    ...overrides,
  };
}

describe('MeetingRecordingPlayer', () => {
  it('renders the caption text for a playable chunk with a transcript', () => {
    const { container } = render(<MeetingRecordingPlayer chunks={[makeChunk()]} />);
    const captionParagraph = container.querySelector('p');
    expect(captionParagraph).not.toBeNull();
    expect(captionParagraph?.textContent).toBe('Alice said we should ship it');
  });

  it('toggles the caption bar when the captions button is clicked', async () => {
    const user = userEvent.setup();
    const { container } = render(<MeetingRecordingPlayer chunks={[makeChunk()]} />);

    expect(container.querySelector('p')?.textContent).toBe('Alice said we should ship it');

    const toggleButton = screen.getByRole('button', { name: /hide captions/i });
    await user.click(toggleButton);
    expect(container.querySelector('p')).toBeNull();

    const showButton = screen.getByRole('button', { name: /show captions/i });
    await user.click(showButton);
    expect(container.querySelector('p')?.textContent).toBe('Alice said we should ship it');
  });

  it('renders the fallback message for a chunk with no transcript_text', () => {
    const chunk = makeChunk({ transcript_text: undefined, upload_status: 'Failed' });
    const { container } = render(<MeetingRecordingPlayer chunks={[chunk]} />);

    const captionParagraph = container.querySelector('p');
    expect(captionParagraph?.textContent).toContain('[this part could not be transcribed]');
  });

  it('renders the fallback message for a chunk with a transcription_error', () => {
    const chunk = makeChunk({
      transcript_text: undefined,
      transcription_error: 'STT service unavailable',
    });
    const { container } = render(<MeetingRecordingPlayer chunks={[chunk]} />);

    const captionParagraph = container.querySelector('p');
    expect(captionParagraph?.textContent).toContain('[this part could not be transcribed]');
    expect(within(container).getByText(/could not be transcribed/i)).toBeInTheDocument();
  });
});
