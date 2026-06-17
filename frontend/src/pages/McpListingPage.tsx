import { useEffect } from 'react';
import { Calendar, Settings, Tag } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { FilterBar, GridView, ItemCard, LoadMoreButton } from '../components/dashboard';
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
    error,
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

  // Show error toast when there's an error
  useEffect(() => {
    if (error) {
      toast.error('Failed to load MCP servers', {
        description: error.message || 'An error occurred while fetching MCP servers. Please try again.',
        duration: 5000,
      });
    }
  }, [error]);

  return (
    <div className="flex flex-col h-full overflow-hidden p-6 gap-6">
      <div className="flex-none">
        <div className="mb-4">
          <h1 className="text-2xl font-semibold tracking-tight">MCP Servers</h1>
          <p className="text-sm text-muted-foreground mt-1">Manage Model Context Protocol (MCP) servers and their configurations</p>
        </div>
        <FilterBar
          searchPlaceholder="Search MCP servers..."
          searchValue={search}
          onSearchChange={setSearch}
        />
      </div>

      <div className="flex-1 overflow-auto">
        {error && !initialLoading && (
          <div className="text-center py-12">
            <p className="text-destructive mb-4">Failed to load MCP servers</p>
            <p className="text-sm text-muted-foreground mb-4">{error.message || 'An error occurred while fetching MCP servers.'}</p>
          </div>
        )}
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
      </div>
    </div>
  );
}
