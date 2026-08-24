import { useEffect } from 'react';
import { Mic } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, GridView, LoadMoreButton, EmptyState } from '@/components/dashboard';
import { useInfiniteScroll } from '@/hooks/useInfiniteScroll';
import { MeetingCard } from '@/components/meetings/MeetingCard';
import { createMeeting, listMeetings, startRecording } from '@/services/meetingApi';
import type { MeetingListItem, MeetingStatus } from '@/types/meeting.types';

const STATUS_FILTER_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'All statuses', value: 'all' },
  { label: 'Recording', value: 'Recording' },
  { label: 'Paused', value: 'Paused' },
  { label: 'Processing', value: 'Stopped' },
  { label: 'Completed', value: 'Completed' },
  { label: 'Failed', value: 'Failed' },
];

export default function MeetingsPage() {
  const navigate = useNavigate();

  const {
    items: meetings,
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
    { page?: number; limit?: number; start?: number; search?: string; status?: string },
    MeetingListItem
  >({
    fetchFn: async (params) => {
      const response = await listMeetings({
        start: params.start,
        limit: params.limit,
        search: params.search,
        status: (params.status as MeetingStatus | undefined) || undefined,
      });
      return {
        data: response.meetings,
        hasMore: response.has_more,
      };
    },
    initialParams: {},
    pageSize: 20,
    debounceMs: 300,
    autoLoad: true,
  });

  const handleEmptyStateQuickStart = async () => {
    try {
      const { meeting_name: meetingName } = await createMeeting({});
      await startRecording(meetingName);
      navigate(`/meetings/${meetingName}/record`);
    } catch (err) {
      toast.error('Could not start recording', {
        description: err instanceof Error ? err.message : 'An unexpected error occurred.',
      });
    }
  };

  useEffect(() => {
    if (error) {
      toast.error('Failed to load meetings', {
        description: error.message || 'An error occurred while fetching meetings. Please try again.',
        duration: 5000,
      });
    }
  }, [error]);

  return (
    <PageFrame
      title="Meetings"
      filters={
        <FilterBar
          searchPlaceholder="Search meetings..."
          searchValue={search}
          onSearchChange={setSearch}
          filters={[
            {
              label: 'Status',
              value: filters.status || 'all',
              options: STATUS_FILTER_OPTIONS,
              onChange: (value) => setFilter('status', value),
            },
          ]}
        />
      }
    >
      {error && !initialLoading && (
        <div className="text-center py-12">
          <p className="text-destructive mb-4">Failed to load meetings</p>
          <p className="text-sm text-steel mb-4">{error.message || 'An error occurred while fetching meetings.'}</p>
        </div>
      )}
      <GridView
        items={meetings}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          search ? (
            <EmptyState
              variant="no-results"
              icon={Mic}
              title="No meetings found"
              filterTerm={search}
              secondaryAction={{ label: 'Clear search', onClick: () => setSearch('') }}
            />
          ) : (
            <EmptyState
              variant="create"
              icon={Mic}
              title="No meetings yet"
              description="Start your first recording — you can add a title and participants later."
              action={{ label: 'Quick start', onClick: handleEmptyStateQuickStart }}
            />
          )
        }
        renderItem={(meeting) => (
          <MeetingCard
            meeting={meeting}
            onClick={() => navigate(`/meetings/${meeting.name}`)}
          />
        )}
        keyExtractor={(meeting) => meeting.name}
      />
      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />
      {!hasMore && meetings.length > 0 && (
        <div className="text-center py-4 text-sm font-body text-steel">
          {total !== undefined ? `Showing all ${total} meetings` : 'No more meetings to load'}
        </div>
      )}
    </PageFrame>
  );
}
