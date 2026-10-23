// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import type { TelegramCheck, TelegramHealth } from '@/services/telegramApi';
import { ChecksList } from './ChecksList';
import { HealthBanner } from './HealthBanner';

const warn: TelegramCheck = { id: 'inline_feedback', label: 'Inline feedback', ok: false, hint: 'x', level: 'warn' };
const pass: TelegramCheck = { id: 'bot_reachable', label: 'Bot reachable', ok: true, hint: '' };

describe('Telegram ChecksList', () => {
	it('shows the warn row with its hint', () => {
		render(<ChecksList checks={[warn]} />);
		expect(screen.getByText('Inline answers')).toBeInTheDocument();
		expect(screen.getByText(/send \/setinlinefeedback and choose Enabled/)).toBeInTheDocument();
		expect(screen.getByLabelText('Needs attention')).toBeInTheDocument();
	});

	it('pass rows show no hint', () => {
		render(<ChecksList checks={[pass]} />);
		expect(screen.getByLabelText('Passed')).toBeInTheDocument();
		expect(screen.getAllByRole('listitem')[0].querySelectorAll('p')).toHaveLength(1);
	});

	it('failed non-warn row is an error', () => {
		render(<ChecksList checks={[{ ...pass, ok: false }]} />);
		expect(screen.getByLabelText('Failed')).toBeInTheDocument();
	});

	it('a warn row does not degrade the banner', () => {
		const h = { health: 'healthy', enabled: true, checks: [pass, warn], checklist: [], last_event_at: null } as unknown as TelegramHealth;
		render(<HealthBanner health={h} onCheck={() => {}} />);
		expect(screen.queryByRole('alert')).toBeNull();
	});
});
