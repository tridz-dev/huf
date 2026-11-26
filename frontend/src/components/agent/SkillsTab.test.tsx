// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { SkillsTab } from './SkillsTab';

const access = { canCreate: true };

vi.mock('@/hooks/permissions/useResourceAccess', () => ({
  useResourceAccess: () => ({ canCreate: access.canCreate, canDelete: true, isLoading: false }),
}));

function renderTab() {
  return render(
    <MemoryRouter>
      <SkillsTab skills={[]} skillOptions={[]} onChange={() => {}} />
    </MemoryRouter>,
  );
}

describe('SkillsTab New skill link', () => {
  beforeEach(() => {
    access.canCreate = true;
  });

  it('links to the new skill form when the user can create skills', () => {
    renderTab();
    expect(screen.getByRole('link', { name: 'New skill' })).toHaveAttribute('href', '/skills/new');
  });

  it('hides the link when the user cannot create skills', () => {
    access.canCreate = false;
    renderTab();
    expect(screen.queryByRole('link', { name: 'New skill' })).toBeNull();
  });
});
