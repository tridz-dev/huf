// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { MeetingFailureCard } from './MeetingFailureCard';

afterEach(() => {
  cleanup();
});

function renderCard(props: Partial<React.ComponentProps<typeof MeetingFailureCard>> = {}) {
  const onRetry = vi.fn();
  render(
    <MemoryRouter>
      <MeetingFailureCard onRetry={onRetry} retrying={false} {...props} />
    </MemoryRouter>,
  );
  return { onRetry };
}

describe('MeetingFailureCard', () => {
  describe('generic failure', () => {
    it('renders the lastError text and no Configure model link, and calls onRetry when Retry is clicked', async () => {
      const user = userEvent.setup();
      const { onRetry } = renderCard({ failedStep: 'Transcription', lastError: 'Something broke upstream' });

      expect(screen.getByText('Something broke upstream')).toBeInTheDocument();
      expect(screen.queryByRole('link', { name: /configure model/i })).not.toBeInTheDocument();

      const retryButton = screen.getByRole('button', { name: /retry/i });
      expect(retryButton).toBeInTheDocument();

      await user.click(retryButton);
      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it('falls back to a default message per failedStep when lastError is not set', () => {
      renderCard({ failedStep: 'Summary', lastError: undefined });
      expect(screen.getByText('Summarizing this meeting failed.')).toBeInTheDocument();
    });
  });

  describe('model-not-configured failure', () => {
    it('renders the explanatory message and a Configure model link with the encoded agent href, and still shows Retry', () => {
      renderCard({ failedStep: 'Model Not Configured' });

      expect(screen.getByText("No AI model is configured for this meeting's summary agent.")).toBeInTheDocument();

      const configureLink = screen.getByRole('link', { name: /configure model/i });
      expect(configureLink).toBeInTheDocument();
      expect(configureLink).toHaveAttribute('href', '/agents/Meeting%20Summary%20Agent');

      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });
  });

  describe('error log disclosure', () => {
    it('renders a View error log trigger and expands it to reveal the log content on click', async () => {
      const user = userEvent.setup();
      renderCard({ failedStep: 'Transcription', lastError: 'oops', errorLog: 'stack trace line 1\nstack trace line 2' });

      const trigger = screen.getByRole('button', { name: /view error log/i });
      expect(trigger).toHaveAttribute('aria-expanded', 'false');

      await user.click(trigger);

      expect(trigger).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByText(/stack trace line 1/)).toBeInTheDocument();
    });

    it('does not render the disclosure when errorLog is empty or undefined', () => {
      renderCard({ failedStep: 'Transcription', lastError: 'oops', errorLog: undefined });
      expect(screen.queryByRole('button', { name: /view error log/i })).not.toBeInTheDocument();
    });
  });

  describe('retrying state', () => {
    it('disables the Retry button and shows the retrying label when retrying is true', async () => {
      const user = userEvent.setup();
      const { onRetry } = renderCard({ failedStep: 'Transcription', lastError: 'oops', retrying: true });

      const retryButton = screen.getByRole('button', { name: /retrying/i });
      expect(retryButton).toBeDisabled();

      await user.click(retryButton);
      expect(onRetry).not.toHaveBeenCalled();
    });
  });
});
