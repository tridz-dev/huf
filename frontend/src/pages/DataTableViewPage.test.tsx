// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { PermissionsContext } from '@/contexts/PermissionsContext';
import { DataTableViewPage } from './DataTableViewPage';

const api = vi.hoisted(() => ({
	getTableSchema: vi.fn(),
	deleteDataTable: vi.fn(),
}));
vi.mock('@/services/dataTableApi', () => api);
vi.mock('@/components/data-table/view/DataTab', () => ({ DataTab: () => null }));
vi.mock('@/components/data-table/view/ActivityTab', () => ({ ActivityTab: () => null }));
vi.mock('@/components/data-table/AgentsTab', () => ({ AgentsTab: () => null }));
vi.mock('@/components/data-table/import/ImportDialog', () => ({ ImportDialog: () => null }));
vi.mock('@/components/data-table/DeleteTableDialog', () => ({ DeleteTableDialog: () => null }));
vi.mock('@/components/data-table/FieldsTab', () => ({ FieldsTab: () => null }));

const schema = {
	name: 'T1',
	table_name: 'Customers',
	doctype_name: 'x',
	description: '',
	icon: '',
	autoname_method: 'Hash',
	title_field_name: '',
	fields: [{ fieldname: 'email', fieldtype: 'Data', label: 'Email' }],
} as never;

function renderPage(capabilities: string[]) {
	const value = {
		hufRole: null,
		capabilities,
		withheldCapabilities: [],
		isLoading: false,
		hasCapability: (c: string) => capabilities.includes(c),
		refresh: async () => {},
	} as never;
	const Where = () => <p>at {useLocation().pathname}</p>;
	render(
		<PermissionsContext.Provider value={value}>
			<MemoryRouter initialEntries={['/data/T1']}>
				<Routes>
					<Route path="/data/:tableId" element={<DataTableViewPage />} />
					<Route path="/data/:tableId/edit" element={<Where />} />
				</Routes>
			</MemoryRouter>
		</PermissionsContext.Provider>,
	);
}

describe('DataTableViewPage Edit fields', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		api.getTableSchema.mockResolvedValue(schema);
	});

	it('navigates to the builder from the overflow menu for table managers', async () => {
		renderPage(['data.tables.manage']);
		await userEvent.click(await screen.findByRole('button', { name: 'More actions for Customers' }));
		await userEvent.click(await screen.findByRole('menuitem', { name: /Edit fields/ }));
		expect(await screen.findByText('at /data/T1/edit')).toBeInTheDocument();
	});

	it('hides Edit fields from users who cannot manage the table', async () => {
		renderPage([]);
		await userEvent.click(await screen.findByRole('button', { name: 'More actions for Customers' }));
		expect(screen.queryByRole('menuitem', { name: /Edit fields/ })).toBeNull();
	});
});
