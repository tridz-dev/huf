import { useEffect, useState } from 'react';
import { Plus, ShieldCheck, Layers, Sparkles, Trash2, Settings, Brain } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { FilterBar, GridView, ItemCard, EmptyState } from '@/components/dashboard';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { getMemoryPolicies, deleteMemoryPolicy } from '@/services/memoryPolicyApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { MemoryPolicyDoc } from '@/types/memory';
import { DeleteMemoryPolicyDialog } from './DeleteMemoryPolicyDialog';

const memoryPolicyStatusFilters = [
  { label: 'All', value: 'all' },
  { label: 'Enabled', value: 'enabled' },
  { label: 'Disabled', value: 'disabled' },
];

export function MemoryPolicyList() {
  const navigate = useNavigate();
  const [pendingDelete, setPendingDelete] = useState<MemoryPolicyDoc | null>(null);
  const [deleting, setDeleting] = useState(false);

  const {
    items: policies,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    filters,
    setFilter,
    loadMore,
    total,
    error,
    reset,
  } = useInfiniteScroll<
    { status?: string; page?: number; limit?: number; start?: number; search?: string },
    MemoryPolicyDoc
  >({
    fetchFn: async (params) => {
      const response = await getMemoryPolicies({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: params.status,
      });

      return {
        data: response.items,
        hasMore: response.hasMore,
        total: response.total,
      };
    },
    initialParams: {},
    pageSize: 20,
    debounceMs: 300,
    autoLoad: true,
  });

  useEffect(() => {
    if (error) {
      toast.error('Failed to load memory policies', {
        description: error.message || 'An error occurred while fetching memory policies.',
        duration: 5000,
      });
    }
  }, [error]);

  const handleDeleteConfirm = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteMemoryPolicy(pendingDelete.name);
      toast.success('Memory policy deleted');
      setPendingDelete(null);
      reset();
    } catch (err) {
      const msg = getFrappeErrorMessage(err);
      toast.error(msg || 'Failed to delete memory policy');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-4">
      <FilterBar
        searchPlaceholder="Search memory policies..."
        searchValue={search}
        onSearchChange={setSearch}
        filters={[
          {
            label: 'Status',
            value: filters.status || 'all',
            options: memoryPolicyStatusFilters,
            onChange: (value) => setFilter('status', value),
          },
        ]}
        primaryAction={{
          label: 'New Policy',
          icon: <Plus className="h-3.5 w-3.5" />,
          onClick: () => navigate('/memory/policies/new'),
        }}
      />

      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load memory policies</p>
          <p className="text-sm text-steel mb-4">
            {error.message || 'An error occurred while fetching memory policies.'}
          </p>
        </div>
      )}

      <GridView
        items={policies}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          <EmptyState
            icon={Brain}
            title="No memory policies"
            description="Create a memory policy to control how agents capture and retrieve long-term memory."
            action={{ label: 'New policy', onClick: () => navigate('/memory/policies/new') }}
          />
        }
        renderItem={(policy) => (
          <ItemCard
            title={policy.policy_name || policy.name}
            description={
              policy.description?.trim() || `${policy.scope_type} scope · ${policy.inject_mode} inject`
            }
            status={{
              label: policy.enabled ? 'Enabled' : 'Disabled',
              variant: policy.enabled ? 'success' : 'secondary',
            }}
            metadata={[
              { label: 'Agent', value: policy.agent || 'Any', icon: ShieldCheck },
              { label: 'Capture', value: policy.capture_mode, icon: Layers },
              { label: 'Inject Mode', value: policy.inject_mode, icon: Layers },
              {
                label: 'Auto-promote',
                value: policy.auto_promote_to_knowledge ? 'Yes' : 'No',
                icon: Sparkles,
              },
            ]}
            actions={[
              {
                icon: Settings,
                label: 'Configure',
                onClick: () => navigate(`/memory/policies/${encodeURIComponent(policy.name)}`),
              },
              {
                icon: Trash2,
                label: 'Delete',
                variant: 'destructive',
                onClick: () => setPendingDelete(policy),
              },
            ]}
            onClick={() => navigate(`/memory/policies/${encodeURIComponent(policy.name)}`)}
          />
        )}
        keyExtractor={(policy) => policy.name}
      />

      {hasMore && (
        <div className="text-center">
          <Button variant="outline" size="sm" disabled={loadingMore} onClick={loadMore}>
            {loadingMore ? 'Loading...' : 'Load more'}
          </Button>
        </div>
      )}
      {!hasMore && policies.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined
            ? `Showing all ${total} memory policies`
            : 'No more memory policies to load'}
        </div>
      )}

      {pendingDelete && (
        <DeleteMemoryPolicyDialog
          open={!!pendingDelete}
          onOpenChange={(open) => !open && setPendingDelete(null)}
          policyName={pendingDelete.policy_name || pendingDelete.name}
          onConfirm={handleDeleteConfirm}
          loading={deleting}
        />
      )}
    </div>
  );
}
