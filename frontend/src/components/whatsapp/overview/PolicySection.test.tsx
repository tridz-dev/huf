// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { PolicySection, type PolicySectionProps } from './PolicySection';

const base: PolicySectionProps = {
	fallbackTemplate: 'hello_again',
	fallbackTemplateLanguage: 'en_US',
	fallbackTemplateApproved: true,
	policy: {
		direct_policy: 'open',
		room_policy: 'allowlist',
		room_sender_policy: 'open',
		mention_required: true,
		pairing_enabled: false,
		default_target: { type: 'Agent', name: 'Support agent' },
	},
	editHref: '/edit',
};

describe('PolicySection', () => {
	it('is closed by default', () => {
		render(<PolicySection {...base} />);
		expect(screen.queryByText(/Outside the 24-hour window/)).toBeNull();
	});

	it('starts expanded with defaultOpen', () => {
		render(<PolicySection {...base} defaultOpen />);
		expect(screen.getByText(/Outside the 24-hour window/)).toBeInTheDocument();
	});

	it('shows rules in plain words when opened', async () => {
		const user = userEvent.setup();
		render(<PolicySection {...base} />);
		await user.click(screen.getByText('Reply rules'));
		expect(screen.getByText('Outside the 24-hour window we send hello_again (en_US).')).toBeInTheDocument();
		expect(screen.getByText('Agent: Support agent')).toBeInTheDocument();
		expect(screen.getByText('Only approved people')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Edit in gateway settings' })).toHaveAttribute('href', '/edit');
	});

	it('warns when no fallback template is set and flags unapproved ones', async () => {
		const user = userEvent.setup();
		const { rerender } = render(<PolicySection {...base} fallbackTemplate={null} policy={{}} />);
		await user.click(screen.getByText('Reply rules'));
		expect(screen.getByText('Replies after 24 hours will fail until you set a fallback template.')).toBeInTheDocument();
		expect(screen.getByText('New people must pair first (default)')).toBeInTheDocument();
		expect(screen.getByText('No default agent')).toBeInTheDocument();
		expect(screen.queryByText('Not set')).toBeNull();
		rerender(<PolicySection {...base} fallbackTemplateApproved={false} />);
		expect(screen.getByText(/hasn't approved/)).toBeInTheDocument();
	});
});
