// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { RoutingOrderCard } from './RoutingOrderCard';
import { numberSummary } from './fixturesSolutions';

describe('RoutingOrderCard', () => {
	it('shows rank, rule, target, Paused tag and Triage assistant', () => {
		render(
			<MemoryRouter>
				<RoutingOrderCard summary={numberSummary()} />
			</MemoryRouter>
		);
		expect(screen.getByText('Keyword: order')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Care' })).toHaveAttribute('href', '/solutions/care');
		expect(screen.getByText('Paused')).toBeInTheDocument();
		expect(screen.getByText('Triage assistant')).toBeInTheDocument();
	});

	it('handles no rules', () => {
		render(
			<MemoryRouter>
				<RoutingOrderCard summary={numberSummary({ routing_order: [] })} />
			</MemoryRouter>
		);
		expect(screen.getByText('No rules')).toBeInTheDocument();
	});
});
