// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { PageFrame } from './PageFrame';
import { UnifiedLayout } from './UnifiedLayout';

vi.mock('../components/app-sidebar', () => ({ AppSidebar: () => null }));
vi.mock('../components/ApprovalsBell', () => ({ ApprovalsBell: () => <span>approvals bell</span> }));
vi.mock('../components/ExecutionApprovalsBell', () => ({ ExecutionApprovalsBell: () => <span>code bell</span> }));
vi.mock('../contexts/PermissionsContext', () => ({ usePermissions: () => ({ hasCapability: () => true }) }));

beforeAll(() => {
	window.matchMedia ??= ((query: string) => ({
		matches: false,
		media: query,
		addEventListener: () => {},
		removeEventListener: () => {},
		addListener: () => {},
		removeListener: () => {},
		dispatchEvent: () => false,
		onchange: null,
	})) as unknown as typeof window.matchMedia;
});

const show = (page: React.ReactNode) =>
	render(
		<MemoryRouter initialEntries={['/mcp']}>
			<UnifiedLayout headerActions={<button>route action</button>}>{page}</UnifiedLayout>
		</MemoryRouter>
	);

describe('PageFrame head bar replacing the topbar', () => {
	it('keeps the route actions and the approval bells', () => {
		show(<PageFrame title="MCP servers">rows</PageFrame>);
		expect(screen.getByRole('button', { name: 'route action' })).toBeTruthy();
		expect(screen.getAllByText('approvals bell')).toHaveLength(1);
		expect(screen.getAllByText('code bell')).toHaveLength(1);
	});

	it("lets the page's own actions win", () => {
		show(
			<PageFrame title="MCP servers" actions={<button>page action</button>}>
				rows
			</PageFrame>
		);
		expect(screen.getByRole('button', { name: 'page action' })).toBeTruthy();
		expect(screen.queryByRole('button', { name: 'route action' })).toBeNull();
	});
});
