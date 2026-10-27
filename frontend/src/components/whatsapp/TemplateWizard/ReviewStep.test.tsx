// @vitest-environment jsdom
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import { validateDraft } from '../template/rules';
import { emptyDraft } from '../template/draft';
import { ReviewStep } from './ReviewStep';

vi.mock('../TemplatePreview', () => ({ TemplatePreview: () => null }));
vi.mock('../template/rules', async (orig) => ({
	...(await orig<typeof import('../template/rules')>()),
	validateDraft: vi.fn(),
}));

const view = () =>
	render(<ReviewStep draft={emptyDraft()} kindLabel="Marketing · Default" isEdit={false} direct={false} />);

describe('ReviewStep checks row', () => {
	beforeEach(() => {
		vi.mocked(validateDraft).mockReset();
	});

	it('shows Ready to send for a valid draft and never prints the JSX source', () => {
		vi.mocked(validateDraft).mockReturnValue({});
		view();
		expect(screen.getByText('Ready to send')).toBeInTheDocument();
		expect(screen.queryByText(/issues\.length/)).toBeNull();
		expect(screen.queryByText(/\?\s*\(/)).toBeNull();
	});

	it('shows the problem count and first issue for an invalid draft', () => {
		vi.mocked(validateDraft).mockReturnValue({ body: 'Body is too long', name: 'Name is required' });
		view();
		expect(screen.getByText('2 problems')).toBeInTheDocument();
		expect(screen.getByText('Body is too long')).toBeInTheDocument();
		expect(screen.queryByText('Ready to send')).toBeNull();
		expect(screen.queryByText(/issues\.length/)).toBeNull();
	});

	it('uses the singular for one problem', () => {
		vi.mocked(validateDraft).mockReturnValue({ name: 'Name is required' });
		view();
		expect(screen.getByText('1 problem')).toBeInTheDocument();
	});
});
