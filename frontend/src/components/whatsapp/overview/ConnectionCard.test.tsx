// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ConnectionCard, type ConnectionCardProps } from './ConnectionCard';

const base: ConnectionCardProps = {
	webhookUrl: 'https://x.test/hook',
	verifyTokenPresent: true,
	phoneNumberId: '123',
	phone: { display: '+1 555', verified_name: 'Acme', quality: 'GREEN' },
	metaLinks: { app_dashboard: 'https://meta.test/app', whatsapp_manager: 'https://meta.test/wm', webhook_config: null },
	integrationSettingsHref: '/settings',
};

describe('ConnectionCard', () => {
	it('renders full data with safe external links', () => {
		render(<ConnectionCard {...base} />);
		expect(screen.getByLabelText('Callback URL')).toHaveValue('https://x.test/hook');
		expect(screen.getByText('Acme')).toBeInTheDocument();
		const link = screen.getByRole('link', { name: /Open Meta app dashboard/ });
		expect(link).toHaveAttribute('target', '_blank');
		expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
		expect(screen.getByText(/saved in this gateway's integration settings/)).toBeInTheDocument();
	});

	it('hides null links and missing details', () => {
		render(
			<ConnectionCard
				{...base}
				verifyTokenPresent={false}
				phoneNumberId={null}
				phone={null}
				metaLinks={{ app_dashboard: null, whatsapp_manager: null, webhook_config: null }}
			/>
		);
		expect(screen.queryByRole('link', { name: /Meta|WhatsApp Manager/ })).toBeNull();
		expect(screen.queryByText('Phone number ID')).toBeNull();
		expect(screen.getByText(/Not set yet/)).toBeInTheDocument();
	});

	it('shows a masked verify token only when passed', () => {
		render(<ConnectionCard {...base} verifyToken="s3cret" />);
		expect(screen.getByLabelText('Verify token')).toHaveAttribute('type', 'password');
	});

	it('never renders a verify token when none is passed', () => {
		const { container } = render(<ConnectionCard {...base} />);
		expect(container.querySelector('input[type="password"]')).toBeNull();
	});
});
