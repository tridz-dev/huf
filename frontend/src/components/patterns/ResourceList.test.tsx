// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Trash2 } from 'lucide-react';
import { OverflowMenu } from './OverflowMenu';
import { ResourceList, ResourceRow } from './ResourceList';

describe('ResourceRow click to open', () => {
	it('opens when the empty part of the row is clicked', async () => {
		const onOpen = vi.fn();
		render(
			<ResourceList label="Docs">
				<ResourceRow title="Invoice" origin="Upload" status={<span>Ready</span>} time="2 days ago" onOpen={onOpen} />
			</ResourceList>,
		);
		// Origin and actions render once for mobile and once for md+, so take the first of each.
		await userEvent.click(screen.getAllByText('Ready')[0]);
		await userEvent.click(screen.getAllByText('Upload')[0]);
		expect(onOpen).toHaveBeenCalledTimes(2);
	});

	it('opens once when the title button is clicked', async () => {
		const onOpen = vi.fn();
		render(
			<ResourceList label="Docs">
				<ResourceRow title="Invoice" onOpen={onOpen} />
			</ResourceList>,
		);
		await userEvent.click(screen.getByRole('button', { name: 'Invoice' }));
		expect(onOpen).toHaveBeenCalledTimes(1);
	});

	it('keeps the title button focusable and activatable from the keyboard', async () => {
		const onOpen = vi.fn();
		render(
			<ResourceList label="Docs">
				<ResourceRow title="Invoice" onOpen={onOpen} />
			</ResourceList>,
		);
		const title = screen.getByRole('button', { name: 'Invoice' });
		title.focus();
		expect(title).toHaveFocus();
		await userEvent.keyboard('{Enter}');
		expect(onOpen).toHaveBeenCalledTimes(1);
	});

	it('does not open when a control in the actions slot is clicked', async () => {
		const onOpen = vi.fn();
		const onAction = vi.fn();
		render(
			<ResourceList label="Docs">
				<ResourceRow title="Invoice" onOpen={onOpen} actions={<button type="button" onClick={onAction}>Quick</button>} />
			</ResourceList>,
		);
		await userEvent.click(screen.getAllByRole('button', { name: 'Quick' })[0]);
		expect(onAction).toHaveBeenCalledTimes(1);
		expect(onOpen).not.toHaveBeenCalled();
	});

	it('does not open when an overflow menu item is chosen', async () => {
		const onOpen = vi.fn();
		const onDelete = vi.fn();
		render(
			<ResourceList label="Docs">
				<ResourceRow
					title="Invoice"
					onOpen={onOpen}
					actions={<OverflowMenu size="icon-sm" label="More actions for Invoice" items={[{ label: 'Delete', icon: Trash2, onSelect: onDelete }]} />}
				/>
			</ResourceList>,
		);
		await userEvent.click(screen.getAllByRole('button', { name: 'More actions for Invoice' })[0]);
		await userEvent.click(await screen.findByRole('menuitem', { name: /Delete/ }));
		expect(onDelete).toHaveBeenCalledTimes(1);
		expect(onOpen).not.toHaveBeenCalled();
	});

	it('is not clickable without onOpen', () => {
		render(
			<ResourceList label="Docs">
				<ResourceRow title="Static" />
			</ResourceList>,
		);
		const row = within(screen.getByRole('list', { name: 'Docs' })).getAllByRole('listitem')[0];
		expect(row).not.toHaveClass('cursor-pointer');
		expect(screen.queryByRole('button', { name: 'Static' })).toBeNull();
	});
});
