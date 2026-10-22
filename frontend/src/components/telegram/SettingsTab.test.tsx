// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('@/lib/frappe-sdk', () => ({ call: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { call } from '@/lib/frappe-sdk';
import { SettingsTab } from './SettingsTab';
import type { TelegramTabProps } from './tabTypes';

const props: TelegramTabProps = {
	gateway: 'TG-1',
	health: null,
	overview: null,
	loading: false,
	checking: false,
	onCheck: () => {},
	onTurnOn: () => {},
	settingsHref: '/x',
};

const settings = {
	success: true,
	gateway: 'TG-1',
	values: { typing_indicator: 1, retry_max_attempts: 4, telegram_agent_allow_group_admin: 0, direct_policy: 'Allow list' },
	options: { direct_policy: ['Disabled', 'Pairing', 'Allow list', 'Open'] },
	unavailable: [],
};

describe('SettingsTab', () => {
	beforeEach(() => {
		vi.mocked(call.get).mockReset().mockResolvedValue({ message: settings });
		vi.mocked(call.post).mockReset().mockResolvedValue({ message: { ...settings, values: { ...settings.values, retry_max_attempts: 6 } } });
	});

	it('starts clean and saves only the changed field', async () => {
		render(<SettingsTab {...props} />);
		const save = await screen.findByRole('button', { name: 'Save changes' });
		expect(save).toBeDisabled();
		fireEvent.change(screen.getByLabelText('Send attempts'), { target: { value: '6' } });
		expect(screen.getByText('1 unsaved change')).toBeInTheDocument();
		fireEvent.click(save);
		await waitFor(() => expect(call.post).toHaveBeenCalled());
		expect(vi.mocked(call.post).mock.calls[0][1]).toEqual({ gateway: 'TG-1', values: { retry_max_attempts: 6 } });
		await waitFor(() => expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled());
	});

	it('warns when group admin actions are turned on', async () => {
		render(<SettingsTab {...props} />);
		await screen.findByText('Agent permissions');
		expect(screen.queryByText(/remove people/)).toBeNull();
		fireEvent.click(screen.getByLabelText('Allow group admin actions'));
		expect(screen.getByRole('note')).toHaveTextContent(/remove people/);
	});

	it('hides fields this site does not have', async () => {
		vi.mocked(call.get).mockResolvedValue({ message: { ...settings, unavailable: ['typing_indicator'] } });
		render(<SettingsTab {...props} />);
		await screen.findByText('Replies');
		expect(screen.queryByLabelText('Typing indicator')).toBeNull();
	});
});
