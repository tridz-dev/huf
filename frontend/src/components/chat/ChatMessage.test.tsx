// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatMessage } from './ChatMessage';
import type { MessageType } from './types';

// CopyButton / MessageActions / Image surface toast notifications — sonner's
// Toaster isn't mounted in these tests, so stub the module.
vi.mock('sonner', () => ({
	toast: { error: vi.fn(), success: vi.fn() },
}));

// ChatMessage reads the current user from context; a bare render has no
// UserProvider (and the real provider would try to hit the Frappe SDK), so
// stub the hook with a fixed user.
vi.mock('@/contexts/UserContext', () => ({
	useUser: () => ({
		user: { name: 'u1', full_name: 'Safwan Test' },
		isLoading: false,
		isAuthenticated: true,
		logout: vi.fn(),
		refreshUser: vi.fn(),
	}),
}));

// These two children have their own heavy rendering pipelines (Streamdown
// markdown + artifact parsing / cycling loading messages). The dispatch logic
// under test lives in ChatMessage itself, so stub them with deterministic
// stand-ins that echo the props ChatMessage passes down.
vi.mock('./MessageContentWithArtifacts', () => ({
	MessageContentWithArtifacts: ({ content }: { content: string }) => (
		<div data-testid="message-content">{content}</div>
	),
}));

vi.mock('./MessageLoadingState', () => ({
	MessageLoadingState: ({ type, toolName }: { type?: string; toolName?: string }) => (
		<div data-testid="loading-state">
			{type ?? 'default'}
			{toolName ? `:${toolName}` : ''}
		</div>
	),
}));

const makeMessage = (overrides: Partial<MessageType> = {}): MessageType => ({
	key: 'msg-1',
	from: 'assistant',
	versions: [{ id: 'v1', content: 'Hello there' }],
	...overrides,
});

const renderMessage = (message: MessageType, props: Partial<Parameters<typeof ChatMessage>[0]> = {}) => {
	const onFeedback = vi.fn();
	const scrollToBottomAfterPaint = vi.fn();
	const utils = render(
		<ChatMessage
			message={message}
			agentName="Test Agent"
			agentColor={null}
			status="ready"
			onFeedback={onFeedback}
			scrollToBottomAfterPaint={scrollToBottomAfterPaint}
			{...props}
		/>
	);
	return { ...utils, onFeedback, scrollToBottomAfterPaint };
};

const toolMessage = (overrides: Partial<MessageType> = {}): MessageType =>
	makeMessage({
		tools: [
			{
				tool_call_id: 'tc-1',
				name: 'get_document',
				description: 'Fetch a document',
				status: 'output-available',
				parameters: { name: 'SO-0001' },
				result: '{"status":"ok"}',
				error: undefined,
			},
		],
		...overrides,
	});

describe('ChatMessage', () => {
	it('renders a user message with the "You" label, user initials and content', () => {
		renderMessage(makeMessage({ from: 'user' }));
		expect(screen.getByText('You')).toBeInTheDocument();
		expect(screen.getByText('ST')).toBeInTheDocument(); // getInitials('Safwan Test')
		expect(screen.getByTestId('message-content')).toHaveTextContent('Hello there');
	});

	it('renders an assistant message with the agent name and agent initials', () => {
		renderMessage(makeMessage());
		expect(screen.getByText('Test Agent')).toBeInTheDocument();
		expect(screen.getByText('TA')).toBeInTheDocument(); // getInitials('Test Agent')
		expect(screen.getByTestId('message-content')).toHaveTextContent('Hello there');
	});

	it('sends thumbs-up feedback with the agent message id for assistant messages', () => {
		const { onFeedback } = renderMessage(makeMessage());
		fireEvent.click(screen.getByLabelText('Mark response helpful'));
		expect(onFeedback).toHaveBeenCalledWith('Thumbs Up', { agentMessageId: 'v1' });
	});

	it('does not render feedback actions on user messages', () => {
		renderMessage(makeMessage({ from: 'user' }));
		expect(screen.queryByLabelText('Mark response helpful')).not.toBeInTheDocument();
		expect(screen.queryByLabelText('Mark response not helpful')).not.toBeInTheDocument();
	});

	it('returns null for Tool Call messages when tool execution details are hidden', () => {
		const { container } = renderMessage(makeMessage({ kind: 'Tool Call' }), {
			showToolExecutionDetails: false,
		});
		expect(container.firstChild).toBeNull();
	});

	it('returns null for tools-only messages when tool execution details are hidden', () => {
		const { container } = renderMessage(
			toolMessage({ versions: [{ id: 'v1', content: '   ' }] }),
			{ showToolExecutionDetails: false }
		);
		expect(container.firstChild).toBeNull();
	});

	it('renders the tool UI and skips content/actions when tools are shown', () => {
		renderMessage(toolMessage());
		expect(screen.getByText('get_document')).toBeInTheDocument();
		// The tools branch replaces the regular message body entirely
		expect(screen.queryByTestId('message-content')).not.toBeInTheDocument();
		// Feedback actions are suppressed while tool details are visible
		expect(screen.queryByLabelText('Mark response helpful')).not.toBeInTheDocument();
	});

	it('shows the loading state for a streaming assistant message with empty content', () => {
		renderMessage(makeMessage({ versions: [{ id: 'v1', content: '' }] }), {
			status: 'streaming',
			loadingType: 'transcribing',
		});
		expect(screen.getByTestId('loading-state')).toHaveTextContent('transcribing');
		expect(screen.queryByTestId('message-content')).not.toBeInTheDocument();
	});

	it('renders the generated image with alt text and fires the scroll callback on load', () => {
		const { scrollToBottomAfterPaint } = renderMessage(
			makeMessage({
				kind: 'Image',
				generatedImage: 'https://example.com/cat.png',
				versions: [{ id: 'v1', content: 'A cat' }],
			})
		);
		const img = screen.getByAltText('A cat');
		expect(img).toHaveAttribute('src', 'https://example.com/cat.png');
		fireEvent.load(img);
		expect(scrollToBottomAfterPaint).toHaveBeenCalledWith(false);
		// The caption content still renders below the image
		expect(screen.getByTestId('message-content')).toHaveTextContent('A cat');
	});

	it('renders a skeleton placeholder for an Image message without generatedImage', () => {
		const { container } = renderMessage(makeMessage({ kind: 'Image' }));
		expect(container.querySelector('img')).not.toBeInTheDocument();
		expect(container.querySelector('[class*="animate-pulse"]')).toBeInTheDocument();
	});

	it('renders the audio player for assistant messages and resolves relative URLs against the Frappe origin', () => {
		const { container } = renderMessage(
			makeMessage({ generatedAudio: '/files/reply.mp3' })
		);
		expect(container.querySelector('audio')).toHaveAttribute(
			'src',
			`${window.location.origin}/files/reply.mp3`
		);
		// The audio branch replaces the text content
		expect(screen.queryByTestId('message-content')).not.toBeInTheDocument();
	});

	it('passes absolute audio URLs through unchanged', () => {
		const { container } = renderMessage(
			makeMessage({ generatedAudio: 'https://cdn.example.com/reply.mp3' })
		);
		expect(container.querySelector('audio')).toHaveAttribute(
			'src',
			'https://cdn.example.com/reply.mp3'
		);
	});

	it('renders the attachment card above the message content', () => {
		renderMessage(
			makeMessage({
				attachment: { name: 'report.pdf', label: 'PDF Document' },
			})
		);
		expect(screen.getByText('report.pdf')).toBeInTheDocument();
		expect(screen.getByText('PDF Document')).toBeInTheDocument();
		expect(screen.getByTestId('message-content')).toHaveTextContent('Hello there');
	});
});
