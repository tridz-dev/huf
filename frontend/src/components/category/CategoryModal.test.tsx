// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';
import { CategoryModal } from './CategoryModal';
import { createCategory } from '@/services/categoryApi';

const adminState = { isAdmin: true };

vi.mock('@/contexts/PermissionsContext', () => ({
  useIsHufAdmin: () => adminState.isAdmin,
}));

vi.mock('@/services/categoryApi', () => ({
  createCategory: vi.fn(),
  updateCategory: vi.fn(),
  deleteCategory: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

const serverError = (message: string, excType = 'ValidationError') => ({
  exc_type: excType,
  _server_messages: JSON.stringify([JSON.stringify({ message })]),
});

function renderCreateModal() {
  return render(
    <CategoryModal
      open
      onOpenChange={() => {}}
      categories={[]}
      selected={null}
      onSave={() => {}}
      refreshCategories={async () => {}}
      onDeleteCategory={async () => {}}
    />,
  );
}

async function submitNewCategory() {
  const addTab = screen.getByRole('tab', { name: 'Add New' });
  fireEvent.mouseDown(addTab);
  fireEvent.click(addTab);
  const nameInput = await screen.findByPlaceholderText('Enter category name');
  fireEvent.change(nameInput, { target: { value: 'Refunds' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create Category' }));
}

describe('CategoryModal create failure toast', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  it('shows the server reason to a System Manager (Huf Admin)', async () => {
    adminState.isAdmin = true;
    vi.mocked(createCategory).mockRejectedValue(serverError('Category name already exists'));
    renderCreateModal();
    await submitNewCategory();
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Failed to create category', {
        description: 'Category name already exists',
      }),
    );
  });

  it('shows a plain permission message to a non-admin', async () => {
    adminState.isAdmin = false;
    vi.mocked(createCategory).mockRejectedValue(
      serverError('Insufficient Permission for Category', 'PermissionError'),
    );
    renderCreateModal();
    await submitNewCategory();
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Failed to create category', {
        description: "You don't have permission to change categories.",
      }),
    );
  });
});
