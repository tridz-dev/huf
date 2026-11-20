// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CreateTableDialog } from './CreateTableDialog';
import { EmptyTables } from './EmptyTables';
import { TablesLedger } from './TablesLedger';
import { agentAccessText, filterRows, isValidTableName, type TableRowModel } from './tableListModel';

const row = (o: Partial<TableRowModel> = {}): TableRowModel => ({
	id: 't1', name: 'Customers', description: 'Who we sell to', group: 'Ungrouped', fields: 7, rows: 1284,
	modified: '', agents: [{ agent: 'a', agent_name: 'Billing agent', actions: ['view', 'edit'] }], ...o,
});

describe('model', () => {
	it('formats agent access text', () => {
		expect(agentAccessText(row())).toBe('Billing agent: read, edit');
		expect(agentAccessText(row({ agents: [] }))).toBe('Used by no agent');
	});
	it('validates names', () => {
		expect(isValidTableName('Customers 2')).toBe(true);
		expect(isValidTableName('_bad')).toBe(false);
		expect(isValidTableName(`a${'b'.repeat(140)}`)).toBe(false);
	});
	it('filters by no-agent and search', () => {
		const rs = [row(), row({ id: 't2', name: 'Orders', agents: [] })];
		expect(filterRows(rs, 'none', '').map((r) => r.id)).toEqual(['t2']);
		expect(filterRows(rs, 'all', 'cust').map((r) => r.id)).toEqual(['t1']);
	});
});

describe('TablesLedger', () => {
	it('shows counts and routes the menu', async () => {
		const onAgentAccess = vi.fn();
		render(<TablesLedger rows={[row()]} onOpen={vi.fn()} onAgentAccess={onAgentAccess} onDelete={vi.fn()} />);
		expect(screen.getAllByText('Billing agent: read, edit')[0]).toBeInTheDocument();
		expect(screen.getByText('1,284 rows · 7 fields')).toBeInTheDocument();
		await userEvent.click(screen.getAllByRole('button', { name: 'More actions for Customers' })[0]);
		await userEvent.click(await screen.findByRole('menuitem', { name: 'Agent access' }));
		expect(onAgentAccess).toHaveBeenCalled();
	});
});

describe('EmptyTables', () => {
	it('says no tables yet and offers starts', async () => {
		const onStart = vi.fn();
		render(<EmptyTables onStart={onStart} onNew={vi.fn()} />);
		expect(screen.getByText('No tables yet')).toBeInTheDocument();
		await userEvent.click(screen.getByText('Paste rows'));
		expect(onStart).toHaveBeenCalledWith('paste');
	});
});

describe('CreateTableDialog', () => {
	it('blocks invalid and duplicate names, then submits', async () => {
		const onCreate = vi.fn().mockResolvedValue(undefined);
		render(<CreateTableDialog open onOpenChange={vi.fn()} existingNames={['Orders']} onCreate={onCreate} />);
		const input = screen.getByLabelText(/Name/);
		await userEvent.type(input, '-x');
		expect(screen.getByRole('alert')).toHaveTextContent('Start with a letter');
		expect(screen.getByRole('button', { name: 'Create table' })).toBeDisabled();
		await userEvent.clear(input);
		await userEvent.type(input, 'orders');
		expect(screen.getByRole('alert')).toHaveTextContent('already exists');
		await userEvent.clear(input);
		await userEvent.type(input, 'Leads');
		await userEvent.click(screen.getByText('CSV or Sheet'));
		await userEvent.click(screen.getByRole('button', { name: 'Create table' }));
		expect(onCreate).toHaveBeenCalledWith({ name: 'Leads', description: '', start: 'csv' });
	});
});
