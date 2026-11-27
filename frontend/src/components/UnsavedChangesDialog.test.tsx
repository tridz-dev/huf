// @vitest-environment jsdom
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { createMemoryRouter, RouterProvider, useBlocker } from 'react-router-dom';
import { UnsavedChangesDialog } from './UnsavedChangesDialog';

function Form() {
	const blocker = useBlocker(true);
	return (
		<div>
			<span>form</span>
			<UnsavedChangesDialog blocker={blocker} />
		</div>
	);
}

function setup() {
	const router = createMemoryRouter(
		[
			{ path: '/', element: <div>home</div> },
			{ path: '/form', element: <Form /> },
			{ path: '/other', element: <div>other</div> },
		],
		{ initialEntries: ['/', '/form'], initialIndex: 1 },
	);
	render(<RouterProvider router={router} />);
	return router;
}

const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 50)); });

describe('UnsavedChangesDialog', () => {
	it('Leave completes a POP (Back) navigation', async () => {
		const router = setup();
		await act(async () => { await router.navigate(-1); });
		fireEvent.click(await screen.findByText('Leave'));
		await settle();
		expect(router.state.location.pathname).toBe('/');
	});

	it('Cancel stays on a POP navigation', async () => {
		const router = setup();
		await act(async () => { await router.navigate(-1); });
		fireEvent.click(await screen.findByText('Cancel'));
		await settle();
		expect(router.state.location.pathname).toBe('/form');
	});

	it('Escape stays', async () => {
		const router = setup();
		await act(async () => { await router.navigate('/other'); });
		fireEvent.keyDown(await screen.findByRole('alertdialog'), { key: 'Escape' });
		await settle();
		expect(router.state.location.pathname).toBe('/form');
	});

	it('Leave completes a PUSH navigation', async () => {
		const router = setup();
		await act(async () => { await router.navigate('/other'); });
		fireEvent.click(await screen.findByText('Leave'));
		await settle();
		expect(router.state.location.pathname).toBe('/other');
	});
});
