// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import type { TelegramBot } from '@/services/telegramApi';
import { CapabilitiesCard } from './CapabilitiesCard';

const bot: TelegramBot = {
	id: 1,
	username: 'huf_bot',
	can_join_groups: true,
	can_connect_to_business: true,
	supports_guest_queries: false,
	supports_join_request_queries: false,
	has_topics_enabled: false,
};

describe('CapabilitiesCard', () => {
	it('lists each mode with On or Off', () => {
		render(<CapabilitiesCard bot={bot} />);
		expect(screen.getAllByRole('listitem')).toHaveLength(5);
		expect(screen.getAllByText('On')).toHaveLength(2);
		expect(screen.getAllByText('Off')).toHaveLength(3);
		expect(screen.getByText(/@huf_bot/)).toBeInTheDocument();
	});

	it('explains when the bot cannot be read', () => {
		render(<CapabilitiesCard bot={null} error="x" />);
		expect(screen.getByText(/could not read this bot/)).toBeInTheDocument();
	});
});
