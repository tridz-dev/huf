// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import type { TelegramCheck, TelegramHealth } from '@/services/telegramApi';
import { HealthBanner } from './HealthBanner';
import { OverviewChecks } from './OverviewChecks';

const JARGON = /doctype|\bSSE\b|webhook|getMe|allowed_updates/i;

const checks: TelegramCheck[] = [
	{ id: 'bot_reachable', label: 'Telegram accepts the bot token', ok: true, state: 'pass', hint: '' },
	{ id: 'webhook_url', label: 'Telegram sends messages to this site', ok: false, state: 'fail', hint: 'Connect to Telegram again so messages come to this site' },
	{ id: 'inline_mode', label: 'Inline mode', ok: false, state: 'warn', hint: 'Turn on inline mode in BotFather: send /setinline.' },
	{ id: 'guest_mode', label: 'Guest questions', ok: true, state: 'off', hint: '' },
];

describe('OverviewChecks', () => {
	it('shows a warn row with its hint', () => {
		render(<OverviewChecks checks={checks} />);
		expect(screen.getByText('Inline mode')).toBeInTheDocument();
		expect(screen.getByText(/send \/setinline/)).toBeInTheDocument();
		expect(screen.getByText('Needs a fix:')).toBeInTheDocument();
	});

	it('shows a fail row with its hint', () => {
		render(<OverviewChecks checks={checks} />);
		expect(screen.getByText(/Connect to Telegram again/)).toBeInTheDocument();
	});

	it('keeps pass and off rows compact: label only, no hint', () => {
		render(<OverviewChecks checks={checks} />);
		expect(screen.getByText('Telegram accepts the bot token')).toBeInTheDocument();
		expect(screen.getByText('Guest questions')).toBeInTheDocument();
		expect(screen.getByText('Not in use')).toBeInTheDocument();
		expect(screen.getAllByRole('listitem')).toHaveLength(4);
		expect(screen.getAllByText(/./, { selector: 'li p.text-xs' })).toHaveLength(2); // fail + warn hints only
	});

	it('uses plain wording', () => {
		const { container } = render(<OverviewChecks checks={checks} />);
		expect(container.textContent).not.toMatch(JARGON);
	});

	it('renders nothing without checks', () => {
		const { container } = render(<OverviewChecks checks={[]} />);
		expect(container).toBeEmptyDOMElement();
	});
});

describe('warn rows and overall health', () => {
	it('a warn row does not turn a healthy bot into an alert', () => {
		const h: TelegramHealth = {
			name: 'TG-1',
			enabled: true,
			health: 'healthy',
			checks: [checks[0], checks[2]],
			checklist: [],
			pending_update_count: 0,
			last_event_at: new Date().toISOString(),
		};
		render(<HealthBanner health={h} onCheck={vi.fn()} />);
		expect(screen.getByRole('status')).toHaveTextContent('Working');
		expect(screen.queryByRole('alert')).toBeNull();
	});
});
