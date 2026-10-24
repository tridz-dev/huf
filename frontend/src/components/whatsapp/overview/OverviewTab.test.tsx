// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { OverviewTab } from './OverviewTab';
import { numberSummary } from './fixturesSolutions';
import { gatewayFixture } from './fixtures';

const getNumberSummary = vi.hoisted(() => vi.fn());
// vitest reports a mock's own rejected promise as unhandled, so a failure is a malformed (null) response.
const failing = async () => null;
vi.mock('@/services/solutionsApi', () => ({ getNumberSummary }));

const props = { loading: false, checking: false, onCheck: vi.fn(), onTurnOn: vi.fn(), settingsHref: '/s', failedEventHref: () => '/f' };
const renderTab = () =>
	render(
		<MemoryRouter>
			<OverviewTab gateway={gatewayFixture()} {...props} />
		</MemoryRouter>
	);

describe('OverviewTab solutions cards', () => {
	beforeEach(() => getNumberSummary.mockReset());

	it('renders the two cards when the summary loads', async () => {
		getNumberSummary.mockResolvedValue(numberSummary());
		renderTab();
		expect(await screen.findByText('Solutions on this number')).toBeInTheDocument();
		expect(screen.getByText('Routing order')).toBeInTheDocument();
		expect(getNumberSummary).toHaveBeenCalledWith(gatewayFixture().name);
	});

	it('hides them when the summary fails', async () => {
		getNumberSummary.mockImplementation(failing);
		renderTab();
		await Promise.resolve();
		expect(screen.queryByText('Routing order')).not.toBeInTheDocument();
		expect(screen.getByText('Connection')).toBeInTheDocument();
	});
});
