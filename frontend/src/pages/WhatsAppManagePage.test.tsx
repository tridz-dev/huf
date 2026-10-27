// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';

import { gatewayFixture } from '@/components/whatsapp/overview/fixtures';

const api = vi.hoisted(() => ({ getSetupStatus: vi.fn(), checkToken: vi.fn() }));
vi.mock('@/services/whatsappHealthApi', async (orig) => ({ ...(await orig<object>()), ...api }));
vi.mock('@/components/whatsapp/TemplatesTab', () => ({ TemplatesTab: ({ gateway }: { gateway?: string }) => <div>templates for {gateway}</div> }));
vi.mock('@/components/whatsapp/MessageLogTab', () => ({
	MessageLogTab: ({ gateway, bridgeAvailable }: { gateway?: string; bridgeAvailable: boolean }) => (
		<div>messages for {gateway} {bridgeAvailable ? 'connected' : 'no-connector'}</div>
	),
}));

import WhatsAppManagePage from './WhatsAppManagePage';

const summary = (connector = true) => ({
	ok: true,
	data: {
		success: true,
		connector_available: connector,
		gateways: [
			{ name: 'GW-1', health: 'healthy', enabled: true },
			{ name: 'GW-2', health: 'blocked', enabled: true },
		],
	},
});
const detail = (name: string) => ({
	ok: true,
	data: { success: true, connector_available: true, accounts: [], gateway: gatewayFixture({ name }) },
});

function Search() {
	return <output data-testid="search">{useLocation().search}</output>;
}
const open = (url: string) =>
	render(
		<MemoryRouter initialEntries={[url]}>
			<WhatsAppManagePage />
			<Search />
		</MemoryRouter>
	);

beforeEach(() => {
	vi.resetAllMocks();
	Element.prototype.scrollIntoView = vi.fn();
	api.getSetupStatus.mockImplementation(async (name?: string) => (name ? detail(name) : summary()));
});

describe('WhatsAppManagePage', () => {
	it('defaults to Overview and writes the gateway to the URL', async () => {
		open('/');
		expect(await screen.findByText(/steps left/)).toBeInTheDocument();
		await waitFor(() => expect(screen.getByTestId('search')).toHaveTextContent('gateway=GW-1'));
		expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Overview', 'Messages', 'Templates', 'Access', 'Settings']);
	});

	it('honours ?tab= and ?gateway= deep links', async () => {
		open('/?tab=templates&gateway=GW-2');
		expect(await screen.findByText('templates for GW-2')).toBeInTheDocument();
		expect(api.getSetupStatus).toHaveBeenCalledWith('GW-2');
	});

	it('switching tabs updates the URL', async () => {
		open('/?gateway=GW-1');
		await screen.findByText(/steps left/);
		await userEvent.click(screen.getByRole('tab', { name: 'Messages' }));
		expect(screen.getByTestId('search')).toHaveTextContent('tab=messages');
		expect(screen.getByText(/messages for GW-1 connected/)).toBeInTheDocument();
	});

	it('an in-app checklist anchor opens Settings and scrolls to the section', async () => {
		open('/');
		await userEvent.click(await screen.findByRole('link', { name: 'Add app secret' }));
		await waitFor(() => expect(screen.getByTestId('search')).toHaveTextContent('tab=settings'));
		expect((await screen.findAllByText('Edit in gateway settings', { selector: 'a' })).length).toBeGreaterThan(0);
		await waitFor(() => expect(Element.prototype.scrollIntoView).toHaveBeenCalled());
	});

	it('the test message anchor opens Messages', async () => {
		open('/');
		await userEvent.click(await screen.findByRole('link', { name: 'Open WhatsApp' }));
		await waitFor(() => expect(screen.getByTestId('search')).toHaveTextContent('tab=messages'));
		expect(screen.getByTestId('search')).toHaveTextContent('send=1');
	});

	it('the failed-event link carries the event name to Messages', async () => {
		api.getSetupStatus.mockImplementation(async (name?: string) =>
			name
				? { ok: true, data: { success: true, connector_available: true, accounts: [], gateway: gatewayFixture({ name, last_failed_event: { name: 'EV 1', at: '2026-10-14T10:00:00Z', error: null } }) } }
				: summary()
		);
		open('/?gateway=GW-1');
		const link = await screen.findByRole('link', { name: 'View details' });
		expect(link).toHaveAttribute('href', '?tab=messages&gateway=GW-1&event=EV%201');
	});

	it('switching tabs drops one-shot view params', async () => {
		open('/?tab=templates&gateway=GW-1&new=1');
		await screen.findByText('templates for GW-1');
		await userEvent.click(screen.getByRole('tab', { name: 'Messages' }));
		expect(screen.getByTestId('search')).not.toHaveTextContent('new=1');
	});

	it('Check now refetches status and runs the token check', async () => {
		api.checkToken.mockResolvedValue({ ok: true, data: { success: true, valid: true, checked_at: new Date().toISOString() } });
		open('/');
		await userEvent.click(await screen.findByRole('button', { name: 'Check now' }));
		await waitFor(() => expect(api.checkToken).toHaveBeenCalledWith('GW-1'));
		expect(await screen.findByText('Valid', { selector: 'span,div' })).toBeInTheDocument();
		expect(api.getSetupStatus.mock.calls.filter((c) => c[0] === 'GW-1').length).toBe(2);
	});

	it('shows connector-missing only inside Templates and Messages, not page level', async () => {
		api.getSetupStatus.mockImplementation(async (name?: string) => (name ? detail(name) : summary(false)));
		open('/?tab=templates');
		expect(await screen.findByText('WhatsApp Business connector not installed')).toBeInTheDocument();
		await userEvent.click(screen.getByRole('tab', { name: 'Overview' }));
		expect(screen.queryByText('WhatsApp Business connector not installed')).toBeNull();
		await userEvent.click(screen.getByRole('tab', { name: 'Messages' }));
		expect(screen.getByText(/no-connector/)).toBeInTheDocument();
	});

	it('shows the empty state with no gateways and an error with Retry', async () => {
		api.getSetupStatus.mockResolvedValueOnce({ ok: true, data: { success: true, connector_available: true, gateways: [] } });
		const first = open('/');
		expect(await screen.findByText('No WhatsApp gateway yet')).toBeInTheDocument();
		expect(screen.getByText('Connect your first WhatsApp number')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Add a WhatsApp gateway' })).toHaveAttribute('href', '/gateways');
		expect(screen.queryAllByRole('tab')).toHaveLength(0);
		first.unmount();
		api.getSetupStatus.mockResolvedValueOnce({ ok: false, error: 'Boom' });
		open('/');
		expect(await screen.findByText('Boom')).toBeInTheDocument();
		await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
		expect(await screen.findByText(/steps left/)).toBeInTheDocument();
	});

	it('a live token check that fails turns the health blocked and the credentials step off green', async () => {
		api.checkToken.mockResolvedValue({
			ok: true,
			data: { valid: false, token_type: null, expires_at: null, missing_scopes: [], waba_ids: [], phone: null, webhook_subscribed: null, checked_at: null, source: null, message: 'The token has expired.' },
		});
		open('/');
		await screen.findByText(/steps left/);
		const credentialsItem = () => screen.getByText(/^(Add your credentials|Replace access token)$/, { selector: 'p' }).closest('li') as HTMLElement;
		expect(within(credentialsItem()).getByLabelText('Done')).toBeInTheDocument();
		await userEvent.click(screen.getByRole('button', { name: 'Check now' }));
		const alert = await screen.findByRole('alert');
		expect(alert).toHaveTextContent('The token has expired.');
		await waitFor(() => expect(within(credentialsItem()).getByLabelText('Blocked')).toBeInTheDocument());
		expect(within(credentialsItem()).queryByLabelText('Done')).toBeNull();
		// banner, checklist and token card agree: replace the token, same action
		expect(credentialsItem()).toHaveTextContent('Replace access token');
		const links = screen.getAllByRole('link', { name: 'Replace access token' });
		expect(links.length).toBeGreaterThanOrEqual(2);
		for (const l of links) expect(l.getAttribute('href')).toMatch(/#credentials$/);
		expect(screen.getByText(/Meta rejected this token/)).toBeInTheDocument();
	});
});
