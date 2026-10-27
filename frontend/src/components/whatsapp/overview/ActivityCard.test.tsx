// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ActivityCard, type ActivityCardProps } from './ActivityCard';

const empty: ActivityCardProps = {
	lastEventAt: null,
	lastError: null,
	events24h: { received: 0, failed: 0, unrouted: 0, rejected: 0 },
	lastFailedEvent: null,
	unroutedPhoneIds: [],
};

describe('ActivityCard', () => {
	it('shows the empty state', () => {
		render(<ActivityCard {...empty} />);
		expect(screen.getByText('No messages yet')).toBeInTheDocument();
		expect(screen.queryByText('Last error')).toBeNull();
	});

	it('shows stats, failed event link and unrouted notice', () => {
		render(
			<ActivityCard
				{...empty}
				lastEventAt="2026-01-01T10:00:00Z"
				events24h={{ received: 5, failed: 2, unrouted: 1, rejected: 3 }}
				lastFailedEvent={{ name: 'EV-1', at: '2026-01-01T09:00:00Z', error: 'x' }}
				unroutedPhoneIds={['111', '222']}
				failedEventHref={(n) => `/log/${n}`}
			/>
		);
		expect(screen.getByText('5')).toBeInTheDocument();
		expect(screen.getByText('3')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'View details' })).toHaveAttribute('href', '/log/EV-1');
		expect(screen.getByText('Messages arrived for a number no gateway uses: 111, 222')).toBeInTheDocument();
		expect(screen.queryByText('No messages yet')).toBeNull();
	});

	it('truncates a long error and expands it', async () => {
		const user = userEvent.setup();
		const long = 'e'.repeat(300);
		render(<ActivityCard {...empty} lastError={long} />);
		expect(screen.queryByText(long, { exact: false })).toBeNull();
		await user.click(screen.getByRole('button', { name: 'Show more' }));
		expect(screen.getByText(long, { exact: false })).toBeInTheDocument();
	});

	it('shows a short error without a toggle', () => {
		render(<ActivityCard {...empty} lastError="Boom" />);
		expect(screen.getByText('Boom')).toBeInTheDocument();
		expect(screen.queryByRole('button')).toBeNull();
	});
});
