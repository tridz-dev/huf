// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

vi.mock('@/services/procedureProposalApi', () => ({
  proposeProcedureFromRun: vi.fn(),
  acceptProcedureProposal: vi.fn(),
}));

import { proposeProcedureFromRun } from '@/services/procedureProposalApi';
import { ProposeProcedureDialog } from './ProposeProcedureDialog';

describe('ProposeProcedureDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders confirmed-only proposal with plain badges and no warning copy', async () => {
    const mockProposal = {
      proposable: true,
      procedure_graph: {
        entry: 'node-0',
        nodes: [
          {
            id: 'node-0',
            type: 'tool.call',
            config: {
              tool_id: 'erpnext.get_customer',
              input: {
                customer_id: { $from: 'input.customer_id' },
              },
            },
          },
          {
            id: 'node-1',
            type: 'output',
          },
        ],
      },
      input_schema: {
        properties: {
          customer_id: {
            type: 'string',
            'x-confidence': 'prompt' as const,
          },
        },
        required: ['customer_id'],
      },
      unconfirmed_input_fields: [],
      step_count: 1,
      source_run: 'AR-0001',
    };

    vi.mocked(proposeProcedureFromRun).mockResolvedValue(mockProposal);

    render(
      <BrowserRouter>
        <ProposeProcedureDialog agentRunName="AR-0001" open={true} onOpenChange={() => {}} />
      </BrowserRouter>
    );

    // Wait for the async load to resolve by waiting for the name input to appear
    await waitFor(() => {
      expect(screen.getByPlaceholderText('e.g. Draft weekly invoice')).toBeInTheDocument();
    });

    // Assert field badge is present (get all customer_id elements and verify the badge one exists)
    const customerIdBadges = screen.getAllByText(/customer_id/);
    expect(customerIdBadges.length).toBeGreaterThan(0);
    // The badge should have the secondary variant classes
    const badgeElement = customerIdBadges.find((el) => el.className.includes('bg-paper-deep'));
    expect(badgeElement).toBeDefined();

    // Assert the warning text is NOT present
    expect(screen.queryByText(/couldn't confirm where/i)).not.toBeInTheDocument();
  });

  it('renders proposal with unconfirmed field and shows warning copy', async () => {
    const mockProposal = {
      proposable: true,
      procedure_graph: {
        entry: 'node-0',
        nodes: [
          {
            id: 'node-0',
            type: 'tool.call',
            config: {
              tool_id: 'erpnext.create_invoice',
              input: {
                customer_id: { $from: 'input.customer_id' },
                raw_doctype: { $from: 'input.raw_doctype' },
              },
            },
          },
          {
            id: 'node-1',
            type: 'output',
          },
        ],
      },
      input_schema: {
        properties: {
          customer_id: {
            type: 'string',
            'x-confidence': 'prompt' as const,
          },
          raw_doctype: {
            type: 'string',
            'x-confidence': 'unconfirmed' as const,
          },
        },
        required: ['customer_id', 'raw_doctype'],
      },
      unconfirmed_input_fields: ['raw_doctype'],
      step_count: 1,
      source_run: 'AR-0003',
    };

    vi.mocked(proposeProcedureFromRun).mockResolvedValue(mockProposal);

    render(
      <BrowserRouter>
        <ProposeProcedureDialog agentRunName="AR-0003" open={true} onOpenChange={() => {}} />
      </BrowserRouter>
    );

    // Wait for the async load to resolve by waiting for the name input to appear
    await waitFor(() => {
      expect(screen.getByPlaceholderText('e.g. Draft weekly invoice')).toBeInTheDocument();
    });

    // Assert warning text IS present (for 1 unconfirmed field: "this value came")
    expect(screen.getByText(/couldn't confirm where this value came from/i)).toBeInTheDocument();

    // Assert both badges are present
    const customerIdBadges = screen.getAllByText(/customer_id/);
    const rawDocBadges = screen.getAllByText(/raw_doctype/);
    expect(customerIdBadges.length).toBeGreaterThan(0);
    expect(rawDocBadges.length).toBeGreaterThan(0);

    // Assert they have different classes: customer_id should have 'bg-paper-deep' (secondary),
    // raw_doctype should have 'bg-warning-tint' (pill-warning)
    const customerBadge = customerIdBadges.find((el) => el.className.includes('bg-paper-deep'));
    const rawDocBadge = rawDocBadges.find((el) => el.className.includes('bg-warning-tint'));
    expect(customerBadge).toBeDefined();
    expect(rawDocBadge).toBeDefined();
  });

  it('renders non-proposable response and shows refusal branch only', async () => {
    const mockProposal = {
      proposable: false,
      reason: 'Step 2 (some_tool) did not finish cleanly.',
      source_run: 'AR-0002',
    };

    vi.mocked(proposeProcedureFromRun).mockResolvedValue(mockProposal);

    render(
      <BrowserRouter>
        <ProposeProcedureDialog agentRunName="AR-0002" open={true} onOpenChange={() => {}} />
      </BrowserRouter>
    );

    // Wait for the async load to resolve
    await waitFor(() => {
      expect(screen.getByText("These steps can't be saved as a procedure.")).toBeInTheDocument();
    }, { timeout: 3000 });

    // Assert refusal text is shown
    expect(screen.getByText("Step 2 (some_tool) did not finish cleanly.")).toBeInTheDocument();

    // Assert new unconfirmed-input UI is NOT present
    expect(screen.queryByText(/couldn't confirm where/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/need confirming/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/You'll be asked for/i)).not.toBeInTheDocument();
  });
});
