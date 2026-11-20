// @vitest-environment jsdom
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AskField } from './AskField';
import { AttentionBanner } from './AttentionBanner';
import { FilterPills, type FilterPill } from './FilterPills';
import { ProgressRow, progressCopy } from './ProgressRow';
import { highlightTerms, matchStrength } from './ResultCard';
import { StatusSentence } from './StatusSentence';

describe('StatusSentence', () => {
	it('joins parts with a middle dot and drops empty ones', () => {
		render(<StatusSentence tone="ready" parts={['Ready', '1,241 items', false, 'used by 2 agents']} />);
		expect(screen.getByTestId('status-sentence')).toHaveTextContent('Ready · 1,241 items · used by 2 agents');
	});

	it('carries the tone and becomes a live region only when asked', () => {
		const { rerender } = render(<StatusSentence tone="ready">Ready</StatusSentence>);
		expect(screen.getByTestId('status-sentence')).not.toHaveAttribute('aria-live');
		rerender(<StatusSentence tone="live" live>Importing</StatusSentence>);
		const el = screen.getByRole('status');
		expect(el).toHaveAttribute('data-tone', 'live');
		expect(el.querySelector('[data-tone="live"]')).toHaveClass('motion-safe:animate-blink');
	});

	it('runs the inline action', async () => {
		const onClick = vi.fn();
		render(<StatusSentence tone="attention" action={{ label: 'Review', onClick }}>3 need attention</StatusSentence>);
		await userEvent.click(screen.getByRole('button', { name: 'Review' }));
		expect(onClick).toHaveBeenCalledOnce();
	});
});

const PILLS: FilterPill[] = [
	{ value: 'all', label: 'All' },
	{ value: 'ready', label: 'Ready', count: 1241 },
	{ value: 'attention', label: 'Needs attention', count: 3, tone: 'attention' },
	{ value: 'skipped', label: 'Skipped', count: 0, hideEmpty: true },
];

function Pills({ onChange }: { onChange?: (v: string) => void }) {
	const [v, setV] = useState('all');
	return <FilterPills label="Filter by status" pills={PILLS} value={v} onChange={(n) => { setV(n); onChange?.(n); }} />;
}

describe('FilterPills', () => {
	it('renders a radio group with counts and hides empty optional pills', () => {
		render(<Pills />);
		expect(screen.getByRole('radiogroup', { name: 'Filter by status' })).toBeInTheDocument();
		expect(screen.getAllByRole('radio')).toHaveLength(3);
		expect(screen.getByRole('radio', { name: /Ready/ })).toHaveTextContent('1,241');
		expect(screen.getByRole('radio', { name: 'All' })).toHaveAttribute('aria-checked', 'true');
	});

	it('selects on click and tones the attention count', async () => {
		const onChange = vi.fn();
		render(<Pills onChange={onChange} />);
		const att = screen.getByRole('radio', { name: /Needs attention/ });
		expect(att.querySelector('[data-testid="filter-count"]')).toHaveClass('text-warning');
		await userEvent.click(att);
		expect(onChange).toHaveBeenCalledWith('attention');
		expect(att).toHaveAttribute('aria-checked', 'true');
	});

	it('moves selection with arrow keys (roving tabindex)', async () => {
		render(<Pills />);
		screen.getByRole('radio', { name: 'All' }).focus();
		await userEvent.keyboard('{ArrowRight}');
		const ready = screen.getByRole('radio', { name: /Ready/ });
		expect(ready).toHaveAttribute('aria-checked', 'true');
		expect(ready).toHaveFocus();
		expect(ready).toHaveAttribute('tabindex', '0');
	});
});

describe('ProgressRow', () => {
	it('is determinate with counts, ETA and a progressbar value', () => {
		render(<ProgressRow label="Importing" source="S3 · bucket/" done={1240} total={3000} eta="about 2 min left" />);
		const row = screen.getByTestId('progress-row');
		expect(row).toHaveAttribute('data-mode', 'determinate');
		expect(screen.getByRole('status')).toHaveTextContent('Importing from S3 · bucket/ — 1,240 of 3,000 · about 2 min left');
		expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
		expect(screen.getByRole('progressbar')).toHaveAttribute('data-state', 'loading');
	});

	it('is indeterminate with found-so-far copy when the total is unknown', () => {
		render(<ProgressRow label="Finding files" done={412} noun="files" eta="ignored" />);
		expect(screen.getByTestId('progress-row')).toHaveAttribute('data-mode', 'indeterminate');
		expect(screen.getByRole('status')).toHaveTextContent('412 files found so far');
		expect(screen.getByRole('status')).not.toHaveTextContent('ignored');
		expect(screen.getByRole('progressbar')).toHaveAttribute('data-state', 'indeterminate');
	});

	it('cancels', async () => {
		const onCancel = vi.fn();
		render(<ProgressRow label="Importing" done={1} total={2} onCancel={onCancel} />);
		await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(onCancel).toHaveBeenCalledOnce();
	});

	it('formats copy edge cases', () => {
		expect(progressCopy({ done: 0 })).toBe('Starting…');
		expect(progressCopy({ done: 5, total: 3 })).toBe('3 of 3');
	});
});

describe('AskField', () => {
	it('focuses on "/" from the page but not from another field', async () => {
		render(
			<>
				<input aria-label="other" />
				<AskField value="" onChange={() => {}} placeholder="Ask a question" />
			</>,
		);
		await userEvent.keyboard('/');
		expect(screen.getByRole('searchbox', { name: 'Ask a question' })).toHaveFocus();
		screen.getByLabelText('other').focus();
		await userEvent.keyboard('/');
		expect(screen.getByLabelText('other')).toHaveFocus();
	});
});

describe('AttentionBanner and ResultCard helpers', () => {
	it('hides at count 0', () => {
		render(<AttentionBanner message="none" count={0} />);
		expect(screen.queryByTestId('attention-banner')).toBeNull();
	});

	it('marks query terms and maps scores to words', () => {
		const { container } = render(<p>{highlightTerms('Annual plans get a refund.', 'refund annual a')}</p>);
		expect(Array.from(container.querySelectorAll('mark')).map((m) => m.textContent)).toEqual(['Annual', 'refund']);
		expect(matchStrength(0.8)).toBe('high');
		expect(matchStrength(0.6)).toBe('good');
		expect(matchStrength(0.1)).toBe('weak');
	});
});
