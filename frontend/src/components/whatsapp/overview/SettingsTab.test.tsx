// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { gatewayFixture } from './fixtures';
import { OverviewTab } from './OverviewTab';
import { SettingsTab } from './SettingsTab';

const settings = (connectorAvailable: boolean) =>
	render(
		<MemoryRouter>
			<SettingsTab
				gateway={gatewayFixture()}
				accounts={[{ name: 'Acct-1', phone_id: '999', status: 'Active' }]}
				connectorAvailable={connectorAvailable}
				onCheckToken={vi.fn()}
				settingsHref="/app/gateway/GW-1"
			/>
		</MemoryRouter>
	);

describe('SettingsTab', () => {
	it('shows the reply rules expanded', () => {
		settings(true);
		expect(screen.getByText(/Outside the 24-hour window|Replies after 24 hours/)).toBeInTheDocument();
	});

	it('has anchor sections, account info and a Desk link', () => {
		const { container } = settings(true);
		for (const id of ['credentials', 'app-secret', 'enabled']) expect(container.querySelector(`#${id}`)).not.toBeNull();
		expect(screen.getByText('Acct-1 (Active)')).toBeInTheDocument();
		expect(screen.getByText('999')).toBeInTheDocument();
		const link = screen.getAllByRole('link', { name: /Edit in gateway settings/ }).find((a) => a.getAttribute('target') === '_blank')!;
		expect(link).toHaveAttribute('href', '/app/gateway/GW-1');
		expect(link).toHaveAttribute('target', '_blank');
		expect(screen.queryByText(/WhatsApp Business connector app/)).toBeNull();
	});

	it('shows the connector notice inline when it is missing', () => {
		settings(false);
		expect(screen.getByRole('status')).toHaveTextContent('Template management and message history need the WhatsApp Business connector app');
	});
});

describe('OverviewTab states', () => {
	const view = (over: Parameters<typeof gatewayFixture>[0], loading = false) =>
		render(
			<MemoryRouter>
				<OverviewTab gateway={loading ? null : gatewayFixture(over)} loading={loading} checking={false} onCheck={vi.fn()} onTurnOn={vi.fn()} settingsHref="/s" failedEventHref={() => '?tab=messages'} />
			</MemoryRouter>
		);

	it('healthy shows the banner and the checklist steps', () => {
		view({});
		expect(screen.getByText(/Working/)).toBeInTheDocument();
		expect(screen.getByText('2 of 3 steps left')).toBeInTheDocument();
	});

	it.each([
		['degraded', /Replies are failing/],
		['blocked', /Blocked/],
		['not_set_up', /Finish setup/],
		['disabled', /turned off/],
	] as const)('%s renders', (health, text) => {
		view({ health, enabled: health !== 'disabled', events_24h: { received: 1, failed: 2, unrouted: 0, rejected: 0 } });
		expect(screen.getByText(text)).toBeInTheDocument();
	});

	it('disabled offers Turn on', () => {
		view({ health: 'disabled', enabled: false });
		expect(screen.getByRole('button', { name: 'Turn on' })).toBeInTheDocument();
	});

	it('loading shows no checklist', () => {
		view({}, true);
		expect(screen.queryByText(/steps left/)).toBeNull();
	});
});
