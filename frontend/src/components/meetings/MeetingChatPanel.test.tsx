// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// jsdom does not implement scrollIntoView; the component calls it on an
// auto-scroll effect that isn't itself under test here.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}

// This config does not enable RTL's global auto-cleanup, so unmount each
// render explicitly between tests to avoid duplicate DOM nodes.
afterEach(() => {
  cleanup();
});
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/services/meetingChat', () => ({
  askMeeting: vi.fn(),
  reviseSummary: vi.fn(),
  getChatHistory: vi.fn(),
}));

import { askMeeting, getChatHistory, reviseSummary } from '@/services/meetingChat';
import { MeetingChatPanel } from './MeetingChatPanel';
import type { MeetingChatMessage } from '@/types/meeting.types';

const baseProps = {
  meetingName: 'MEETING-001',
  hasTranscript: true,
  hasSummary: true,
  onSummaryRevised: vi.fn(),
};

describe('MeetingChatPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a disabled state when there is no transcript, without loading history', () => {
    render(<MeetingChatPanel {...baseProps} hasTranscript={false} />);

    expect(screen.getByText(/chat is available once a transcript exists/i)).toBeInTheDocument();
    expect(getChatHistory).not.toHaveBeenCalled();
  });

  it('loads and renders chat history on mount when a transcript exists', async () => {
    const rows: MeetingChatMessage[] = [
      { name: 'MSG-1', role: 'user', content: 'What did we decide?' },
      { name: 'MSG-2', role: 'assistant', content: 'You decided to ship on Friday.' },
    ];
    vi.mocked(getChatHistory).mockResolvedValue(rows);

    render(<MeetingChatPanel {...baseProps} />);

    await waitFor(() => {
      expect(screen.getByText('What did we decide?')).toBeInTheDocument();
    });
    expect(screen.getByText('You decided to ship on Friday.')).toBeInTheDocument();
    expect(getChatHistory).toHaveBeenCalledWith('MEETING-001');
  });

  it('sends a question and re-fetches history afterward', async () => {
    const user = userEvent.setup();
    vi.mocked(getChatHistory)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ name: 'MSG-1', role: 'user', content: 'question' }]);
    vi.mocked(askMeeting).mockResolvedValue({ reply: 'an answer', message_name: 'x' });

    render(<MeetingChatPanel {...baseProps} />);

    await waitFor(() => expect(getChatHistory).toHaveBeenCalledTimes(1));

    const input = screen.getByPlaceholderText(/ask a question about this meeting/i);
    await user.type(input, 'question{Enter}');

    await waitFor(() => {
      expect(askMeeting).toHaveBeenCalledWith('MEETING-001', 'question');
    });
    await waitFor(() => {
      expect(getChatHistory).toHaveBeenCalledTimes(2);
    });
  });

  it('shows an inline error bubble when askMeeting resolves with an error payload', async () => {
    const user = userEvent.setup();
    vi.mocked(getChatHistory)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{ name: 'MSG-1', role: 'assistant', content: '', error: 'The model call failed.' }]);
    vi.mocked(askMeeting).mockResolvedValue({ error: 'The model call failed.' });

    render(<MeetingChatPanel {...baseProps} />);

    await waitFor(() => expect(getChatHistory).toHaveBeenCalledTimes(1));

    const input = screen.getByPlaceholderText(/ask a question about this meeting/i);
    await user.type(input, 'question{Enter}');

    await waitFor(() => {
      expect(screen.getByText('The model call failed.')).toBeInTheDocument();
    });
  });

  it('revises the summary and fires onSummaryRevised', async () => {
    const user = userEvent.setup();
    const onSummaryRevised = vi.fn();
    vi.mocked(getChatHistory).mockResolvedValue([]);
    vi.mocked(reviseSummary).mockResolvedValue({ summary: 'new summary text' });

    render(<MeetingChatPanel {...baseProps} onSummaryRevised={onSummaryRevised} />);

    await waitFor(() => expect(getChatHistory).toHaveBeenCalledTimes(1));

    const textarea = screen.getByPlaceholderText(/make the action items more concise/i);
    await user.type(textarea, 'Make it shorter');
    await user.click(screen.getByRole('button', { name: /revise summary/i }));

    await waitFor(() => {
      expect(reviseSummary).toHaveBeenCalledWith('MEETING-001', 'Make it shorter');
    });
    await waitFor(() => {
      expect(onSummaryRevised).toHaveBeenCalledTimes(1);
    });
  });
});
