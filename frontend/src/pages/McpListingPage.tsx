import { Calendar, Settings, Tag } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { PageLayout, FilterBar, GridView, ItemCard, LoadMoreButton } from '../components/dashboard';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { getMCPServers } from '../services/mcpApi';
import { formatTimeAgo } from '../utils/time';
import type { MCPServerDoc } from '../services/mcpApi';

function getStatusVariant(enabled: 0 | 1): 'default' | 'secondary' {
  return enabled === 1 ? 'default' : 'secondary';
}

function getStatusLabel(enabled: 0 | 1): 'enabled' | 'disabled' {
  return enabled === 1 ? 'enabled' : 'disabled';
}

export default function McpListingPage() {
  const navigate = useNavigate();

  const {
    items: servers,
    hasMore,
    initialLoading,
    loadingMore,
    search,
    setSearch,
    loadMore,
    total,
  } = useInfiniteScroll<
    { page?: number; limit?: number; start?: number; search?: string },
    MCPServerDoc
  >({
    fetchFn: async (params) => {
      const response = await getMCPServers({
        page: params.page,
        limit: params.limit,
        start: params.start,
        search: params.search,
      });

      // Handle both old (array) and new (paginated) response formats
      if (Array.isArray(response)) {
        return {
          data: response,
          hasMore: false,
          total: response.length,
        };
      }

      // Convert PaginatedMCPServersResponse to PaginatedResponse format
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

  return (
    <PageLayout
      subtitle="Manage Model Context Protocol (MCP) servers and their configurations"
      filters={
        <FilterBar
          searchPlaceholder="Search MCP servers..."
          searchValue={search}
          onSearchChange={setSearch}
        />
      }
    >
      <GridView
        items={servers}
        columns={{ sm: 1, md: 2, lg: 3 }}
        loading={initialLoading}
        emptyState={
          <div className="text-center py-12">
            <p className="text-muted-foreground mb-4">No MCP servers found.</p>
          </div>
        }
        renderItem={(server) => {
          const status = getStatusLabel(server.enabled);
          return (
            <ItemCard
              title={server.server_name || server.name}
              description={server.description?.slice(0, 100) || 'No description'}
              status={{
                label: status,
                variant: getStatusVariant(server.enabled),
              }}
              metadata={[
                ...(server.tool_namespace ? [{ label: 'Namespace', value: server.tool_namespace, icon: Tag }] : []),
                { label: 'Last Sync', value: server.last_sync ? formatTimeAgo(server.last_sync) : 'Never', icon: Calendar },
              ]}
              actions={[
                {
                  icon: Settings,
                  label: 'Configure',
                  onClick: () => navigate(`/mcp/${server.name}`),
                },
              ]}
              onClick={() => navigate(`/mcp/${server.name}`)}
            />
          );
        }}
        keyExtractor={(server) => server.name}
      />
      <LoadMoreButton
        hasMore={hasMore}
        loading={loadingMore}
        onLoadMore={loadMore}
        disabled={!!search || initialLoading}
      />
      {!hasMore && servers.length > 0 && (
        <div className="text-center py-4 text-sm text-muted-foreground">
          {total !== undefined ? `Showing all ${total} MCP servers` : 'No more MCP servers to load'}
        </div>
      )}
    </PageLayout>
  );
}
