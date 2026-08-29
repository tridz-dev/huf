// @vitest-environment jsdom
//
// Component tests for ChatMessage (see docs/testing/CURRENT_STATE.md §6 for
// the behavioral contracts these pin down) plus a render-list duplicate-id
// test against ChatMessageList's rendering path. Follows the jsdom +
// Testing Library pattern established in components/ui/badge.test.tsx.
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { toast } from 'sonner';

import { ChatMessage } from './ChatMessage';
import type { MessageType } from './types';

// vitest.config.ts doesn't set `test.globals`, so Testing Library's
// auto-cleanup (which relies on a global `afterEach`) isn't wired up
// implicitly — clean up the DOM after every test explicitly instead,
// otherwise later tests in this file see leftover nodes from earlier ones.
afterEach(() => {
	cleanup();
});

vi.mock('sonner', () => ({
	toast: {
		info: vi.fn(),
		success: vi.fn(),
		error: vi.fn(),
	},
}));

// ChatMessage doesn't call any backend service directly for tool-call
// approve/deny (there is none — see the TODO(tool-call-approval-api) in
// ChatMessage.tsx), but it does route all real backend calls through
// `@/lib/frappe-sdk`'s `call`. Mock it so we can assert it is never invoked
// by the approve/deny buttons, and so the real FrappeApp client (which talks
// to `window.location.origin`) never gets constructed in this jsdom test.
//
// `db.getDocList` must resolve to an array (not the default `vi.fn()`
// undefined return): ChatMessage now also renders via
// `useProcedureRunLookup`/`useProcedureRunSummaries`
// (agentProcedureRunApi.ts's `getProcedureRunsForToolCalls`), added by the
// Agent Procedure feature merged in from `pre-develop`. That call does
// `for (const row of rows)` over the resolved value; an unmocked `undefined`
// throws "rows is not iterable" as an unhandled rejection, which crashes
// the render for any test with more than one ChatMessage instance mounted
// (the duplicate-id test below).
vi.mock('@/lib/frappe-sdk', () => ({
	call: { post: vi.fn(), get: vi.fn() },
	db: { getDoc: vi.fn(), getDocList: vi.fn().mockResolvedValue([]) },
	auth: { getLoggedInUser: vi.fn() },
	frappe: {},
}));

const noop = () => {};

function baseMessage(overrides: Partial<MessageType> = {}): MessageType {
	return {
		key: 'msg-1',
		from: 'user',
		versions: [{ id: 'v-1', content: 'Hello there' }],
		...overrides,
	};
}

function renderMessage(message: MessageType, statusOverride: 'submitted' | 'streaming' | 'ready' | 'error' = 'ready') {
	return render(
		<MemoryRouter>
			<ChatMessage
				message={message}
				status={statusOverride}
				onFeedback={noop}
				scrollToBottomAfterPaint={noop}
			/>
		</MemoryRouter>
	);
}

describe('ChatMessage — basic rendering', () => {
	it('renders a user message with its text content', () => {
		renderMessage(baseMessage({ from: 'user', versions: [{ id: 'v-1', content: 'Hello there' }] }));

		expect(screen.getByText('Hello there')).toBeInTheDocument();
	});

	it('renders an assistant message with its text content', () => {
		renderMessage(
			baseMessage({
				key: 'msg-2',
				from: 'assistant',
				versions: [{ id: 'v-2', content: 'I can help with that.' }],
			})
		);

		expect(screen.getByText('I can help with that.')).toBeInTheDocument();
	});

	it('applies different structural classes for user vs assistant (role-based styling)', () => {
		const { container: userContainer } = renderMessage(
			baseMessage({ from: 'user', versions: [{ id: 'v-1', content: 'User text' }] })
		);
		expect(userContainer.querySelector('.is-user')).not.toBeNull();
		expect(userContainer.querySelector('.is-assistant')).toBeNull();

		const { container: assistantContainer } = renderMessage(
			baseMessage({ key: 'msg-3', from: 'assistant', versions: [{ id: 'v-3', content: 'Assistant text' }] })
		);
		expect(assistantContainer.querySelector('.is-assistant')).not.toBeNull();
		expect(assistantContainer.querySelector('.is-user')).toBeNull();
	});
});

describe('ChatMessage — tool-call rendering', () => {
	it('renders the tool name and arguments for a message with tool-call content', async () => {
		const user = userEvent.setup();
		const message = baseMessage({
			key: 'AR-0001',
			from: 'assistant',
			versions: [{ id: 'v-4', content: '' }],
			tools: [
				{
					tool_call_id: 'call-1',
					name: 'search_knowledge_base',
					description: 'search_knowledge_base',
					status: 'output-available',
					parameters: { query: 'refund policy' },
					result: '{"hits": 3}',
					error: undefined,
				},
			],
		});

		renderMessage(message);

		// Tool name is shown in the (single-tool) ToolHeader.
		expect(screen.getByText('search_knowledge_base')).toBeInTheDocument();

		// Arguments/output only mount once the collapsible row is expanded
		// (Radix Collapsible doesn't render ToolContent's children while
		// closed) — expand it via the same trigger a user would click.
		await user.click(screen.getByText('search_knowledge_base'));

		expect(screen.getByText(/query: "refund policy"/)).toBeInTheDocument();
	});
});

describe('ChatMessage — tool-call approve/deny is UI-only (TODO(tool-call-approval-api))', () => {
	it('clicking Allow on a pending-approval tool call shows a toast but calls no backend API', async () => {
		const user = userEvent.setup();
		const { call } = await import('@/lib/frappe-sdk');

		const message = baseMessage({
			key: 'AR-0002',
			from: 'assistant',
			versions: [{ id: 'v-5', content: '' }],
			tools: [
				{
					tool_call_id: 'call-2',
					name: 'delete_customer_record',
					description: 'delete_customer_record',
					status: 'approval-requested',
					parameters: { id: 'CUST-1' },
					result: undefined,
					error: undefined,
				},
			],
		});

		renderMessage(message);

		await user.click(screen.getByRole('button', { name: 'Allow' }));

		expect(toast.info).toHaveBeenCalledWith("Approving tool calls isn't wired up yet.");
		expect(call.post).not.toHaveBeenCalled();
		expect(call.get).not.toHaveBeenCalled();
	});

	it('clicking Deny on a pending-approval tool call shows a toast but calls no backend API', async () => {
		const user = userEvent.setup();
		const { call } = await import('@/lib/frappe-sdk');

		const message = baseMessage({
			key: 'AR-0003',
			from: 'assistant',
			versions: [{ id: 'v-6', content: '' }],
			tools: [
				{
					tool_call_id: 'call-3',
					name: 'delete_customer_record',
					description: 'delete_customer_record',
					status: 'approval-requested',
					parameters: { id: 'CUST-2' },
					result: undefined,
					error: undefined,
				},
			],
		});

		renderMessage(message);

		await user.click(screen.getByRole('button', { name: 'Deny' }));

		expect(toast.info).toHaveBeenCalledWith("Denying tool calls isn't wired up yet.");
		expect(call.post).not.toHaveBeenCalled();
		expect(call.get).not.toHaveBeenCalled();
	});
});

describe('ChatMessage — lifecycle run-status states render distinguishably', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	// Read from ChatMessage.tsx: `showLoading` renders MessageLoadingState for
	// Queued/Started; Success has no runStatus and shows the plain content;
	// Failed renders ChatErrorCard via `message.error`. There is no dedicated
	// "status badge" sub-component — the state is expressed through which of
	// these three branches renders, so we assert on that observable split.
	// MessageLoadingState (loading-messages.json) cycles through several
	// randomized copy strings, so we can't assert on exact text — the stable
	// signal is the BrainCircuit icon it renders (`lucide-brain-circuit`),
	// distinct from the ChatErrorCard/content branches below.
	it('Queued renders the loading state (BrainCircuit icon), not the final content', () => {
		const { container } = renderMessage(
			baseMessage({
				key: 'AR-Q',
				from: 'assistant',
				runStatus: 'Queued',
				versions: [{ id: 'v-q', content: '' }],
			}),
			'submitted'
		);

		expect(container.querySelector('.lucide-brain-circuit')).not.toBeNull();
	});

	it('Started renders the loading state as well (indistinguishable from Queued in the UI)', () => {
		const { container } = renderMessage(
			baseMessage({
				key: 'AR-S',
				from: 'assistant',
				runStatus: 'Started',
				versions: [{ id: 'v-s', content: '' }],
			}),
			'submitted'
		);

		expect(container.querySelector('.lucide-brain-circuit')).not.toBeNull();
	});

	it('Success (no runStatus, has content) renders the final message content, not the loading state', () => {
		const { container } = renderMessage(
			baseMessage({
				key: 'AR-OK',
				from: 'assistant',
				runStatus: undefined,
				versions: [{ id: 'v-ok', content: 'All done.' }],
			}),
			'ready'
		);

		expect(screen.getByText('All done.')).toBeInTheDocument();
		expect(container.querySelector('.lucide-brain-circuit')).toBeNull();
	});

	it('Failed renders the error card instead of content or loading state', () => {
		const { container } = renderMessage(
			baseMessage({
				key: 'AR-FAIL',
				from: 'assistant',
				runStatus: 'Failed',
				error: 'The run timed out.',
				versions: [{ id: 'v-fail', content: '' }],
			}),
			'error'
		);

		expect(screen.getByText('The run timed out.')).toBeInTheDocument();
		expect(container.querySelector('.lucide-brain-circuit')).toBeNull();
	});
});

describe('ChatMessage list rendering — duplicate message ids are NOT deduplicated', () => {
	// This documents actual current behavior (per docs/testing/CURRENT_STATE.md
	// §6): nothing in the render path keys/dedupes by id before mapping to
	// JSX. If a hypothetical persistence bug produced two Agent Messages with
	// the same id in the messages array, React would render two separate DOM
	// nodes (with a duplicate-key console warning), not merge them into one.
	it('renders two DOM nodes when the same message id appears twice in the list', () => {
		const duplicated: MessageType = baseMessage({
			key: 'DUP-1',
			from: 'assistant',
			versions: [{ id: 'DUP-1', content: 'Duplicate content' }],
		});

		render(
			<MemoryRouter>
				{[duplicated, { ...duplicated }].map((message) => (
					// React key intentionally NOT unique here (both are
					// `message.key`), mirroring how ChatMessageList keys its
					// `.map()` — see ChatMessageList.tsx `key={message.key}`.
					// eslint-disable-next-line react/no-array-index-key
					<ChatMessage
						key={message.key}
						message={message}
						status="ready"
						onFeedback={noop}
						scrollToBottomAfterPaint={noop}
					/>
				))}
			</MemoryRouter>
		);

		expect(screen.getAllByText('Duplicate content')).toHaveLength(2);
	});
});
