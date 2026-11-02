// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { SolutionsOnNumberCard } from './SolutionsOnNumberCard';
import { numberSummary } from './fixturesSolutions';

const renderCard = (s = numberSummary()) =>
	render(
		<MemoryRouter>
			<SolutionsOnNumberCard gateway="GW 1" summary={s} />
		</MemoryRouter>
	);

describe('SolutionsOnNumberCard', () => {
	it('lists rows with status, meter or n/a, open links and the shared note', () => {
		renderCard();
		expect(screen.getAllByText('Orders').length).toBeGreaterThan(0);
		expect(screen.getByRole('meter', { name: /Orders/ })).toHaveAttribute('aria-valuenow', '42');
		expect(screen.getByText('n/a')).toBeInTheDocument();
		expect(screen.getByText('Paused')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: /Open Orders/ })).toHaveAttribute('href', '/solutions/orders');
		expect(screen.getByRole('link', { name: /Add solution/ })).toHaveAttribute('href', '/solutions/new?gateway=GW%201');
		expect(screen.getByText(/share this number's quality rating/)).toBeInTheDocument();
		expect(screen.queryByText(/replies to no one yet/)).not.toBeInTheDocument();
	});

	it('shows the no-solution band when nothing is live', () => {
		renderCard(numberSummary({ solutions: [], routing_order: [] }));
		expect(screen.getByText('This number replies to no one yet.')).toBeInTheDocument();
		expect(screen.queryByText(/share this number/)).not.toBeInTheDocument();
	});
});
