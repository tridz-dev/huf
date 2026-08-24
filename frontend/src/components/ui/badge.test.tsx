// @vitest-environment jsdom
//
// Proof-of-concept component test: confirms the jsdom + Testing Library +
// user-event setup actually works end to end (render, query, interaction),
// using Badge — a small, purely presentational component with no business
// logic or backend dependency.
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Badge } from '@/components/ui/badge';

describe('Badge', () => {
	it('renders its children as text content', () => {
		render(<Badge>Queued</Badge>);

		expect(screen.getByText('Queued')).toBeInTheDocument();
	});

	it('applies the requested variant and size classes', () => {
		render(
			<Badge variant="pill-success" size="sm">
				Success
			</Badge>
		);

		const badge = screen.getByText('Success');
		expect(badge).toHaveClass('bg-good-tint');
		expect(badge).toHaveClass('text-[10px]');
	});

	it('forwards DOM event handlers (user-event interaction works)', async () => {
		const user = userEvent.setup();
		const onClick = vi.fn();

		render(<Badge onClick={onClick}>Clickable</Badge>);
		await user.click(screen.getByText('Clickable'));

		expect(onClick).toHaveBeenCalledTimes(1);
	});
});
