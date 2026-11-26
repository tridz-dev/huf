// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FieldsTab } from '../FieldsTab';
import { AgentsTab } from '../AgentsTab';
import { fieldRulesText } from './fieldRules';
import { ToolSignaturePanel } from './ToolSignaturePanel';

const api = vi.hoisted(() => ({
	getTableToolSignature: vi.fn(),
	getTableAgentActivity: vi.fn(),
	getTableAgentAccess: vi.fn(),
	setTableAgentAccess: vi.fn(),
}));
vi.mock('@/services/dataTableApi', () => api);
vi.mock('@/services/agentApi', () => ({ getAgents: vi.fn().mockResolvedValue([]) }));

const schema = {
	name: 'T1', table_name: 'Customers', doctype_name: 'x', description: '', icon: '', autoname_method: 'Hash', title_field_name: '',
	fields: [
		{ fieldname: 'email', fieldtype: 'Data', label: 'Email', reqd: 1, unique: 1 },
		{ fieldname: 'age', fieldtype: 'Int', label: 'Age' },
	],
} as never;

beforeEach(() => {
	vi.clearAllMocks();
	api.getTableToolSignature.mockRejectedValue(new Error('missing'));
	api.getTableAgentActivity.mockResolvedValue([
		{ agent: 'Bot', tool: 'delete_customers', status: 'Blocked', timestamp: 'now' },
	]);
	api.getTableAgentAccess.mockResolvedValue([{ agent: 'A1', agent_name: 'Billing', actions: ['view'], tools: [] }]);
});

describe('fieldRulesText', () => {
	it('lists rules', () => {
		expect(fieldRulesText({ reqd: 1, unique: 1 } as never)).toBe('Required, Unique');
		expect(fieldRulesText({} as never)).toBe('No rules');
	});
});

describe('FieldsTab', () => {
	it('renders fields with rules', () => {
		render(<MemoryRouter><FieldsTab schema={schema} tableId="T1" onChanged={() => {}} /></MemoryRouter>);
		expect(screen.getByText('Email')).toBeInTheDocument();
		expect(screen.getAllByText('Required, Unique')[0]).toBeInTheDocument();
	});

	it('shows Add field to managers and navigates to the builder', async () => {
		const Where = () => <p>builder {useLocation().pathname}</p>;
		render(
			<MemoryRouter initialEntries={['/data/T1?tab=fields']}>
				<Routes>
					<Route path="/data/:tableId" element={<FieldsTab schema={schema} tableId="T1" onChanged={() => {}} canManage />} />
					<Route path="/data/:tableId/edit" element={<Where />} />
				</Routes>
			</MemoryRouter>,
		);
		await userEvent.click(screen.getByRole('button', { name: /Add field/ }));
		expect(await screen.findByText('builder /data/T1/edit')).toBeInTheDocument();
	});

	it('hides Add field from users who cannot manage the table', () => {
		render(<MemoryRouter><FieldsTab schema={schema} tableId="T1" onChanged={() => {}} /></MemoryRouter>);
		expect(screen.queryByRole('button', { name: /Add field/ })).toBeNull();
	});
});

describe('AgentsTab', () => {
	it('shows matrix, empty signature state and blocked call', async () => {
		render(<MemoryRouter><AgentsTab schema={schema} tableId="T1" /></MemoryRouter>);
		expect(await screen.findByText('Billing')).toBeInTheDocument();
		expect(await screen.findByText(/Tool details are not available/)).toBeInTheDocument();
		expect(await screen.findByText('Blocked')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: /Playground/ })).toHaveAttribute('href', '/playground');
	});

	it('saves optimistically and rolls back on error', async () => {
		api.setTableAgentAccess.mockRejectedValue(new Error('no'));
		render(<MemoryRouter><AgentsTab schema={schema} tableId="T1" /></MemoryRouter>);
		const edit = await screen.findByRole('checkbox', { name: 'Edit for Billing' });
		await userEvent.click(edit);
		await waitFor(() => expect(api.setTableAgentAccess).toHaveBeenCalledWith('T1', 'A1', ['view', 'edit']));
		await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Edit for Billing' })).not.toBeChecked());
	});
});

describe('ToolSignaturePanel grant filtering', () => {
	const sigTools = ['view', 'view', 'create', 'edit', 'delete'].map((action, i) => ({
		action, tool_name: `tool_${i}`, description: `d${i}`, params: [],
	}));
	it('shows only tools matching granted actions, and a message when none', async () => {
		api.getTableToolSignature.mockResolvedValue({ tools: sigTools });
		api.getTableAgentAccess.mockResolvedValue([{ agent: 'A1', agent_name: 'B', actions: ['view'], tools: [] }]);
		const { unmount } = render(<ToolSignaturePanel tableId="T1" />);
		expect(await screen.findAllByText(/^d[01]$/)).toHaveLength(2);
		expect(screen.queryByText('d4')).toBeNull();
		unmount();
		api.getTableAgentAccess.mockResolvedValue([]);
		render(<ToolSignaturePanel tableId="T1" />);
		expect(await screen.findByText(/No agent has access/)).toBeInTheDocument();
	});
});
