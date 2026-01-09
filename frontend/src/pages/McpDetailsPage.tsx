import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Form } from '../components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';
import { getMCPServer, createMCPServer, updateMCPServer, syncMCPTools, updateMCPTool, type MCPServerDoc } from '../services/mcpApi';
import { getFrappeErrorMessage } from '../lib/frappe-error';
import { MCPHeader } from '../components/mcp/MCPHeader';
import { DetailsTab } from '../components/mcp/DetailsTab';
import { ConnectionTab } from '../components/mcp/ConnectionTab';
import { ToolsTab } from '../components/mcp/ToolsTab';
import { mcpFormSchema, type MCPFormValues, type MCPTool } from '../components/mcp/types';
import { createFormSubmitHandler, type TabFieldMapping } from '../utils/formValidation';

export function McpDetailsPage() {
  const { mcpId } = useParams<{ mcpId: string }>();
  const navigate = useNavigate();
  const isNew = mcpId === 'new';

  // Tab configuration - single source of truth
  const tabConfig = {
    details: {
      label: 'Details',
      fields: ['server_name', 'enabled', 'description', 'tool_namespace', 'timeout_seconds'], // server_name only shown/required for new servers
      default: true,
      disabled: false,
    },
    connection: {
      label: 'Connection',
      fields: ['transport_type', 'server_url', 'auth_type', 'auth_header_name', 'auth_header_value'],
      default: false,
      disabled: false,
    },
    tools: {
      label: 'Tools',
      fields: ['enable_auto_sync'], // Tools tab has enable_auto_sync field
      default: false,
      disabled: isNew, // Disabled for new MCP creation
    },
  } as const;

  // Extract derived values from tab config (memoized to avoid recreating on every render)
  const validTabs = useMemo(() => Object.keys(tabConfig), []);
  const defaultTab = useMemo(
    () => Object.entries(tabConfig).find(([_, config]) => config.default)?.[0] || validTabs[0],
    [validTabs]
  );
  const tabFieldMapping: TabFieldMapping = useMemo(
    () => Object.fromEntries(
      Object.entries(tabConfig).map(([key, config]) => [key, [...config.fields]])
    ),
    []
  );
  const tabLabels = useMemo(
    () => Object.fromEntries(
      Object.entries(tabConfig).map(([key, config]) => [key, config.label])
    ),
    []
  );
  
  // State to track active tab from URL hash
  const [activeTab, setActiveTab] = useState<string>(() => {
    const hashFromUrl = window.location.hash.slice(1);
    return (hashFromUrl && validTabs.includes(hashFromUrl)) ? hashFromUrl : defaultTab;
  });
  
  // Listen for hash changes (back/forward navigation)
  useEffect(() => {
    const handleHashChange = () => {
      const hashFromUrl = window.location.hash.slice(1);
      const tab = (hashFromUrl && validTabs.includes(hashFromUrl)) ? hashFromUrl : defaultTab;
      setActiveTab(tab);
    };
    
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [defaultTab, validTabs]);

  // Handler to update tab in URL hash
  const handleTabChange = (value: string) => {
    setActiveTab(value);
    // Only set hash if it's not the default tab, or clear hash if switching back to default
    if (value === defaultTab) {
      // Clear hash when switching to default tab
      window.history.replaceState(null, '', window.location.pathname);
    } else {
      // Set hash for non-default tabs
      window.location.hash = value;
    }
  };

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [syncing, setSyncing] = useState(false);

  const form = useForm<MCPFormValues>({
    resolver: zodResolver(mcpFormSchema),
    defaultValues: {
      server_name: '',
      enabled: true,
      description: '',
      tool_namespace: '',
      timeout_seconds: undefined,
      transport_type: 'http',
      server_url: '',
      auth_type: 'none',
      auth_header_name: '',
      auth_header_value: '',
      enable_auto_sync: false,
    },
  });

  const watchEnabled = form.watch('enabled');
  const isDirty = form.formState.isDirty;
  const [lastSync, setLastSync] = useState<string | undefined>();

  // Load MCP server data when id is available (only for edit mode)
  useEffect(() => {
    if (mcpId && !isNew) {
      getMCPServer(mcpId).then((data: MCPServerDoc) => {
        form.reset({
          server_name: data.server_name || '',
          enabled: data.enabled === 1,
          description: data.description || '',
          tool_namespace: data.tool_namespace || '',
          timeout_seconds: data.timeout_seconds,
          transport_type: data.transport_type || 'http',
          server_url: data.server_url || '',
          auth_type: data.auth_type || 'none',
          auth_header_name: data.auth_header_name || '',
          auth_header_value: '', // Don't load the encrypted value
          enable_auto_sync: data.enable_auto_sync === 1,
        });
        
        // Load last_sync
        setLastSync(data.last_sync);
        
        // Load tools from child table
        if (data.tools && Array.isArray(data.tools)) {
          setTools(data.tools as MCPTool[]);
        } else {
          setTools([]);
        }
        
        setLoading(false);
      }).catch((error) => {
        console.error('Error loading MCP server:', error);
        const errorMessage = getFrappeErrorMessage(error);
        toast.error(errorMessage || 'Failed to load MCP server details');
        setLoading(false);
      });
    } else if (isNew) {
      // New MCP server mode - form already has default values
      setLoading(false);
      setTools([]);
    }
  }, [mcpId, isNew, form]);

  const onSubmit = async (values: MCPFormValues) => {
    setSaving(true);
    try {
      // Convert form values to MCPServerDoc format
      const mcpData: Partial<MCPServerDoc> = {
        server_name: values.server_name,
        enabled: values.enabled ? 1 : 0,
        description: values.description || '',
        tool_namespace: values.tool_namespace || '',
        timeout_seconds: values.timeout_seconds,
        transport_type: values.transport_type,
        server_url: values.server_url,
        auth_type: values.auth_type || 'none',
        auth_header_name: values.auth_header_name || '',
        auth_header_value: values.auth_header_value || '',
        enable_auto_sync: values.enable_auto_sync ? 1 : 0,
      };

      if (isNew) {
        // Create new MCP server
        const newMCP = await createMCPServer(mcpData);
        toast.success('MCP server created successfully!');
        // Reset form state with the created server's values
        form.reset({
          server_name: newMCP.server_name || '',
          enabled: newMCP.enabled === 1,
          description: newMCP.description || '',
          tool_namespace: newMCP.tool_namespace || '',
          timeout_seconds: newMCP.timeout_seconds,
          transport_type: newMCP.transport_type || 'http',
          server_url: newMCP.server_url || '',
          auth_type: newMCP.auth_type || 'none',
          auth_header_name: newMCP.auth_header_name || '',
          auth_header_value: '', // Don't reset the encrypted value
          enable_auto_sync: newMCP.enable_auto_sync === 1,
        });
        
        // Load tools if available
        if (newMCP.tools && Array.isArray(newMCP.tools)) {
          setTools(newMCP.tools as MCPTool[]);
        }
        
        // Navigate to the edit page with the new server's ID
        navigate(`/mcp/${newMCP.name}`);
      } else if (mcpId) {
        // Update existing MCP server
        await updateMCPServer(mcpId, mcpData);
        toast.success('MCP server updated successfully!');
        // Reset form state with the updated values to mark form as clean
        form.reset({
          server_name: values.server_name,
          enabled: values.enabled,
          description: values.description,
          tool_namespace: values.tool_namespace,
          timeout_seconds: values.timeout_seconds,
          transport_type: values.transport_type,
          server_url: values.server_url,
          auth_type: values.auth_type,
          auth_header_name: values.auth_header_name,
          auth_header_value: '', // Don't reset the encrypted value
          enable_auto_sync: values.enable_auto_sync,
        });
        
        // Reload tools after update
        if (mcpId) {
          getMCPServer(mcpId).then((updatedData: MCPServerDoc) => {
            if (updatedData.tools && Array.isArray(updatedData.tools)) {
              setTools(updatedData.tools as MCPTool[]);
            }
          }).catch((error) => {
            console.error('Error reloading tools:', error);
          });
        }
      }
    } catch (error) {
      console.error(`Error ${isNew ? 'creating' : 'updating'} MCP server:`, error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || `Failed to ${isNew ? 'create' : 'update'} MCP server. Please try again.`);
    } finally {
      setSaving(false);
    }
  };

  // Memoize the form submit handler to avoid recreating it on every render
  const handleFormSubmit = useMemo(
    () => createFormSubmitHandler(form, activeTab, tabFieldMapping, tabLabels, onSubmit),
    [form, activeTab, tabFieldMapping, tabLabels, onSubmit]
  );

  // Show save button for new servers or when form is dirty
  const showSaveButton = isNew || isDirty;

  // Handle tool sync
  const handleSyncTools = async () => {
    if (!mcpId || isNew) {
      toast.error('Please save the MCP server first before syncing tools');
      return;
    }

    setSyncing(true);
    try {
      const result = await syncMCPTools(mcpId);
      if (result.success) {
        toast.success(`Successfully synced ${result.tool_count || 0} tools`);
        // Reload MCP server to get updated tools
        const updatedData = await getMCPServer(mcpId);
        if (updatedData.tools && Array.isArray(updatedData.tools)) {
          setTools(updatedData.tools as MCPTool[]);
        }
        // Update last_sync state
        if (updatedData.last_sync) {
          setLastSync(updatedData.last_sync);
        }
      } else {
        toast.error(result.error || 'Failed to sync tools');
      }
    } catch (error) {
      console.error('Error syncing tools:', error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || 'Failed to sync tools');
    } finally {
      setSyncing(false);
    }
  };

  // Handle tool toggle
  const handleToolToggle = async (toolName: string, enabled: boolean) => {
    if (!mcpId || isNew) {
      return;
    }

    try {
      // Update tool optimistically
      const updatedTools: MCPTool[] = tools.map((tool) =>
        tool.name === toolName ? { ...tool, enabled: (enabled ? 1 : 0) as 0 | 1 } : tool
      );
      setTools(updatedTools);

      // Update via API
      await updateMCPTool(mcpId, toolName, enabled);
      toast.success(`Tool ${enabled ? 'enabled' : 'disabled'} successfully`);
      
      // Reload to ensure sync
      const updatedData = await getMCPServer(mcpId);
      if (updatedData.tools && Array.isArray(updatedData.tools)) {
        setTools(updatedData.tools as MCPTool[]);
      }
    } catch (error) {
      console.error('Error toggling tool:', error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || 'Failed to update tool');
      // Revert on error
      const updatedData = await getMCPServer(mcpId);
      if (updatedData.tools && Array.isArray(updatedData.tools)) {
        setTools(updatedData.tools as MCPTool[]);
      }
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-muted-foreground">Loading MCP server...</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6 max-w-6xl mx-auto">
        <MCPHeader
          form={form}
          watchEnabled={watchEnabled}
          isNew={isNew}
          showSaveButton={showSaveButton}
          saving={saving}
          onSave={handleFormSubmit}
        />

        <Form {...form}>
          <form onSubmit={handleFormSubmit} className="space-y-6">
            <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                {Object.entries(tabConfig).map(([tabKey, config]) => (
                  <TabsTrigger key={tabKey} value={tabKey} disabled={config.disabled}>
                    {config.label}
                  </TabsTrigger>
                ))}
              </TabsList>

              <TabsContent value="details" className="space-y-4">
                <DetailsTab form={form} isNew={isNew} />
              </TabsContent>

              <TabsContent value="connection" className="space-y-4">
                <ConnectionTab form={form} />
              </TabsContent>

              <TabsContent value="tools" className="space-y-4">
                <ToolsTab
                  form={form}
                  tools={tools}
                  lastSync={lastSync}
                  onToolToggle={handleToolToggle}
                  onSync={handleSyncTools}
                  syncing={syncing}
                />
              </TabsContent>
            </Tabs>
          </form>
        </Form>
      </div>
    </div>
  );
}
