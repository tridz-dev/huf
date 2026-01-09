import { useState, useEffect, useMemo } from 'react';
import { Search } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { MCPServerCard } from './MCPServerCard';
import { getMCPServers } from '@/services/mcpApi';
import type { MCPServerDoc } from '@/services/mcpApi';
import { toast } from 'sonner';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

interface SelectMCPServersModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedServers: MCPServerDoc[];
  onAddServers: (servers: MCPServerDoc[]) => void;
}

export function SelectMCPServersModal({
  open,
  onOpenChange,
  selectedServers,
  onAddServers,
}: SelectMCPServersModalProps) {
  const [allServers, setAllServers] = useState<MCPServerDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedServerIds, setSelectedServerIds] = useState<Set<string>>(
    new Set(selectedServers.map((s) => s.name))
  );

  // Load MCP servers when modal opens
  useEffect(() => {
    if (open) {
      setLoading(true);
      // Call without params to get all servers as array (backward compatible)
      getMCPServers()
        .then((response) => {
          // Handle both array and paginated response formats
          const servers = Array.isArray(response) ? response : response.items;
          setAllServers(servers);
          setLoading(false);
        })
        .catch((error) => {
          console.error('Error loading MCP servers:', error);
          const errorMessage = getFrappeErrorMessage(error);
          toast.error(errorMessage || 'Failed to load MCP servers');
          setLoading(false);
        });
      
      // Reset filters and selection when opening
      setSearchQuery('');
      setSelectedServerIds(new Set(selectedServers.map((s) => s.name)));
    }
  }, [open, selectedServers]);

  // Update selected server IDs when selectedServers prop changes
  useEffect(() => {
    if (open) {
      setSelectedServerIds(new Set(selectedServers.map((s) => s.name)));
    }
  }, [selectedServers, open]);

  // Filter servers based on search
  const filteredServers = useMemo(() => {
    return allServers.filter((server) => {
      // Search filter - search by name (server_name) and description
      const matchesSearch =
        searchQuery === '' ||
        (server.server_name || server.name).toLowerCase().includes(searchQuery.toLowerCase()) ||
        server.description?.toLowerCase().includes(searchQuery.toLowerCase());

      return matchesSearch;
    });
  }, [allServers, searchQuery]);

  const handleServerToggle = (server: MCPServerDoc) => {
    const newSelectedIds = new Set(selectedServerIds);
    if (newSelectedIds.has(server.name)) {
      newSelectedIds.delete(server.name);
    } else {
      newSelectedIds.add(server.name);
    }
    setSelectedServerIds(newSelectedIds);
  };

  const handleAdd = () => {
    const serversToAdd = filteredServers.filter((server) =>
      selectedServerIds.has(server.name)
    );
    
    // Only add servers that aren't already selected
    const newServers = serversToAdd.filter(
      (server) => !selectedServers.some((ss) => ss.name === server.name)
    );

    if (newServers.length === 0) {
      toast.info('No new MCP servers selected');
      return;
    }

    onAddServers(newServers);
    toast.success(`Added ${newServers.length} MCP server${newServers.length > 1 ? 's' : ''}`);
    onOpenChange(false);
  };

  const selectedCount = filteredServers.filter((server) =>
    selectedServerIds.has(server.name)
  ).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[700px] h-[80vh] flex flex-col p-0">
        <DialogHeader className="px-6 pt-6 pb-4">
          <DialogTitle>Select MCP Servers</DialogTitle>
          <DialogDescription>
            Choose MCP servers to connect to this agent. Select multiple servers at once.
          </DialogDescription>
        </DialogHeader>

        {/* Filters */}
        <div className="flex flex-col gap-3 px-6 pb-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search MCP servers by name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        {/* Server List */}
        <div className="flex-1 overflow-y-auto min-h-0 px-6 space-y-2 pb-2">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-muted-foreground">Loading MCP servers...</div>
            </div>
          ) : filteredServers.length === 0 ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-muted-foreground">
                {searchQuery
                  ? 'No MCP servers match your search'
                  : 'No MCP servers available'}
              </div>
            </div>
          ) : (
            filteredServers.map((server) => (
              <MCPServerCard
                key={server.name}
                server={server}
                selected={selectedServerIds.has(server.name)}
                onSelect={handleServerToggle}
                compact
              />
            ))
          )}
        </div>

        {/* Footer */}
        <DialogFooter className="flex items-center justify-between border-t px-6 py-4">
          <div className="text-sm text-muted-foreground">
            {selectedCount > 0 ? (
              <>
                {selectedCount} server{selectedCount > 1 ? 's' : ''} selected
                {selectedCount !== filteredServers.length && (
                  <> • {filteredServers.length} total</>
                )}
              </>
            ) : (
              <>{filteredServers.length} server{filteredServers.length !== 1 ? 's' : ''} available</>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={handleAdd} disabled={selectedCount === 0}>
              Add {selectedCount > 0 && `(${selectedCount})`}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

