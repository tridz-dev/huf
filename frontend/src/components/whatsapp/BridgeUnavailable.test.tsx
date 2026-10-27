// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const perms = vi.hoisted(() => ({ admin: true }));
vi.mock('@/contexts/PermissionsContext', () => ({ useIsHufAdmin: () => perms.admin }));
import { LoadError } from './BridgeUnavailable';

const raw = "MySQLdb.OperationalError: (1054, \"Unknown column 'phone_number_id' in 'SELECT'\")";

beforeEach(() => { perms.admin = true; });

describe('LoadError', () => {
  it('shows plain messages as they are', () => {
    render(<LoadError message="Gateway not found." />);
    expect(screen.getByText('Gateway not found.')).toBeInTheDocument();
    expect(screen.queryByText('Technical details')).toBeNull();
  });

  it('hides server exceptions behind Technical details for admins', async () => {
    render(<LoadError message={raw} />);
    expect(screen.getByText(/Something went wrong while loading this page/)).toBeInTheDocument();
    expect(screen.queryByText(raw)).toBeNull();
    await userEvent.click(screen.getByText('Technical details'));
    expect(screen.getByText(raw)).toBeInTheDocument();
  });

  it('never renders the exception text for non-admins', () => {
    perms.admin = false;
    render(<LoadError message={raw} />);
    expect(screen.getByText(/Something went wrong/)).toBeInTheDocument();
    expect(screen.queryByText('Technical details')).toBeNull();
    expect(screen.queryByText(raw)).toBeNull();
  });
});
