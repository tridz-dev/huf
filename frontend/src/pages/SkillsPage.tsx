import { useEffect, useState } from 'react';
import { Sparkles, Settings, Trash2, Ban, CheckCircle2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../components/ui/alert-dialog';
import { PageFrame } from '@/layouts/PageFrame';
import { Button } from '@/components/ui/button';
import { FilterBar, GridView, ItemCard, LoadMoreButton, EmptyState } from '../components/dashboard';
import { ExperimentalBadge } from '../components/common/ExperimentalBadge';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getSkills, deleteSkill, updateSkill } from '../services/skillApi';
import { formatTimeAgo } from '../utils/time';
import type { SkillDoc } from '../types/skill.types';

const skillStatuses = [
  { label: 'All Statuses', value: 'all' },
  { label: 'Active', value: 'Active' },
  { label: 'Draft', value: 'Draft' },
  { label: 'Error', value: 'Error' },
  { label: 'Disabled', value: 'Disabled' },
];

const sourceTypes = [
  { label: 'All Sources', value: 'all' },
  { label: 'Local', value: 'Local' },
  { label: 'Git', value: 'Git' },
  { label: 'Common Destination', value: 'Common Destination' },
  { label: 'App Provided', value: 'App Provided' },
];

function getStatusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'Active':
      return 'default';
    case 'Draft':
      return 'secondary';
    case 'Error':
      return 'destructive';
    case 'Disabled':
      return 'outline';
    default:
      return 'secondary';
  }
}

export function SkillsPage() {
  const navigate = useNavigate();
  const [deleteSkillTarget, setDeleteSkillTarget] = useState<SkillDoc | null>(null);
  const [deleting, setDeleting] = useState(false);

  const {
    items: skills,
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
  } = useInfiniteScroll<
    { status?: string; source_type?: string; page?: number; limit?: number; start?: number; search?: string },
    SkillDoc
  >({
    fetchFn: async (params) => {
      const response = await getSkills({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
        status: params.status,
        source_type: params.source_type,
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
      toast.error('Failed to load skills', {
        description: error.message || 'An error occurred while fetching skills.',
        duration: 5000,
      });
    }
  }, [error]);

  const handleToggleStatus = async (skill: SkillDoc) => {
    const nextStatus = skill.status === 'Disabled' ? 'Active' : 'Disabled';
    try {
      await updateSkill(skill.name, { status: nextStatus });
      toast.success(nextStatus === 'Disabled' ? 'Skill disabled' : 'Skill enabled');
      window.location.reload();
    } catch (err) {
      toast.error('Failed to update skill', {
        description: err instanceof Error ? err.message : 'An error occurred.',
      });
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteSkillTarget) return;
    setDeleting(true);
    try {
      await deleteSkill(deleteSkillTarget.name);
      toast.success('Skill deleted');
      setDeleteSkillTarget(null);
      window.location.reload();
    } catch (err) {
      toast.error('Failed to delete skill', {
        description: err instanceof Error ? err.message : 'An error occurred.',
      });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <PageFrame
      title="Skills"
      badge={<ExperimentalBadge />}
      subtitle="Manage reusable skill bundles for your agents"
      actions={<Button onClick={() => navigate('/skills/new')}>New skill</Button>}
      filters={
        <FilterBar
          searchPlaceholder="Search skills..."
          searchValue={search}
          onSearchChange={setSearch}
          filters={[
            {
              label: 'Status',
              value: filters.status || 'all',
              options: skillStatuses,
              onChange: (value) => setFilter('status', value),
            },
            {
              label: 'Source',
              value: filters.source_type || 'all',
              options: sourceTypes,
              onChange: (value) => setFilter('source_type', value),
            },
          ]}
        />
      }
    >
      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load skills</p>
          <p className="text-sm text-muted-foreground mb-4">
            {error.message || 'An error occurred while fetching skills.'}
          </p>
        </div>
      )}
      <GridView
        items={skills}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          <EmptyState
            icon={Sparkles}
            title="No skills"
            description="Create a skill to get started."
            action={{ label: 'New skill', onClick: () => navigate('/skills/new') }}
          />
        }
        renderItem={(skill) => (
          <ItemCard
            title={skill.title || skill.skill_name || skill.name}
            description={skill.description?.slice(0, 100) || 'No description'}
            icon={Sparkles}
            status={{
              label: skill.status || 'Draft',
              variant: getStatusVariant(skill.status),
            }}
            metadata={[
              { label: 'Source', value: skill.source_type || 'Local' },
              { label: 'Version', value: skill.version || '-' },
              { label: 'Updated', value: skill.modified ? formatTimeAgo(skill.modified) : '-' },
            ]}
            actions={[
              {
                icon: Settings,
                label: 'Configure',
                onClick: () => navigate(`/skills/${skill.name}`),
              },
            ]}
            menuIcon={Settings}
            menuActions={[
              {
                icon: skill.status === 'Disabled' ? CheckCircle2 : Ban,
                label: skill.status === 'Disabled' ? 'Enable' : 'Disable',
                onClick: () => handleToggleStatus(skill),
              },
              {
                icon: Trash2,
                label: 'Delete Skill',
                variant: 'destructive',
                onClick: () => setDeleteSkillTarget(skill),
              },
            ]}
            onClick={() => navigate(`/skills/${skill.name}`)}
          />
        )}
        keyExtractor={(skill) => skill.name}
      />
      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />
      {!hasMore && skills.length > 0 && (
        <div className="text-center py-4 text-sm text-muted-foreground">
          {total !== undefined ? `Showing all ${total} skills` : 'No more skills to load'}
        </div>
      )}
      <AlertDialog open={!!deleteSkillTarget} onOpenChange={(open) => !open && setDeleteSkillTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Delete skill "{deleteSkillTarget?.title || deleteSkillTarget?.skill_name || deleteSkillTarget?.name}"?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes the skill. Skills attached to an agent cannot be deleted —
              remove them from any agent first.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteConfirm} disabled={deleting}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageFrame>
  );
}

export default SkillsPage;
