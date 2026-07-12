// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ToolOutput, ToolHeader, Tool } from './tool';
import type { ExtendedToolState } from './types';

describe('ToolOutput', () => {
	it('renders nothing when there is neither output nor errorText', () => {
		const { container } = render(<ToolOutput output={undefined} errorText={undefined} />);
		expect(container.firstChild).toBeNull();
	});

	it('renders a JSON code block for object output', async () => {
		const { container } = render(<ToolOutput output={{ status: 'ok', count: 2 }} errorText={undefined} />);
		expect(screen.getByText('Result')).toBeInTheDocument();
		// CodeBlock highlights via Prism inside a useEffect (async), and Prism
		// splits the text across nested token <span>s, so no single text node
		// ever contains the full string — check the <pre>'s combined
		// textContent instead of screen.findByText.
		await waitFor(() => {
			expect(container.querySelector('pre')?.textContent).toContain('"status": "ok"');
		});
	});

	it('renders a JSON code block for string output', async () => {
		const { container } = render(<ToolOutput output={'{"raw": true}'} errorText={undefined} />);
		await waitFor(() => {
			expect(container.querySelector('pre')?.textContent).toContain('"raw": true');
		});
	});

	it('renders the errorText label and message when errorText is set', () => {
		render(<ToolOutput output={undefined} errorText="Connection refused" />);
		expect(screen.getByText('Error')).toBeInTheDocument();
		expect(screen.getByText('Connection refused')).toBeInTheDocument();
	});

	it('prefers the "Error" label over "Result" when both output and errorText are present', () => {
		render(<ToolOutput output={{ partial: true }} errorText="Timed out" />);
		expect(screen.getByText('Error')).toBeInTheDocument();
		expect(screen.queryByText('Result')).not.toBeInTheDocument();
	});
});

describe('ToolHeader', () => {
	const renderHeader = (state: ExtendedToolState, title?: string) =>
		render(
			<Tool>
				<ToolHeader type="tool-get_document" state={state} title={title} />
			</Tool>
		);

	it('falls back to a type-derived title when none is given', () => {
		renderHeader('output-available');
		expect(screen.getByText('get_document')).toBeInTheDocument();
	});

	it('uses the explicit title when provided', () => {
		renderHeader('output-available', 'Fetch Document');
		expect(screen.getByText('Fetch Document')).toBeInTheDocument();
	});

	it.each([
		['input-streaming', 'Pending'],
		['input-available', 'Running'],
		['approval-requested', 'Awaiting Approval'],
		['approval-responded', 'Responded'],
		['output-available', 'Completed'],
		['output-error', 'Error'],
		['output-denied', 'Denied'],
	] as const)('shows the "%s" status as "%s"', (state, label) => {
		renderHeader(state);
		expect(screen.getByText(label)).toBeInTheDocument();
	});
});
