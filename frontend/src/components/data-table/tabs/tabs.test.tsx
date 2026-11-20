// @vitest-environment jsdom
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FieldsTab } from '../FieldsTab';
import { AgentsTab } from '../AgentsTab';
import { fieldRulesText } from './fieldRules';

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
