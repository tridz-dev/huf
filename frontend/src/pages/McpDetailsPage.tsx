import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Form } from '../components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';
import { getMCPServer, createMCPServer, updateMCPServer, type MCPServerDoc } from '../services/mcpApi';
import { getFrappeErrorMessage } from '../lib/frappe-error';
import { MCPHeader } from '../components/mcp/MCPHeader';
import { DetailsTab } from '../components/mcp/DetailsTab';
import { ConnectionTab } from '../components/mcp/ConnectionTab';
import { mcpFormSchema, type MCPFormValues } from '../components/mcp/types';

export function McpDetailsPage() {
  const { mcpId } = useParams<{ mcpId: string }>();
  const navigate = useNavigate();
  const isNew = mcpId === 'new';

  // Get active tab from URL hash, default to "details"
  const validTabs = ['details', 'connection', 'tools'];
  
  // State to track active tab from URL hash
  const [activeTab, setActiveTab] = useState<string>(() => {
    const hashFromUrl = window.location.hash.slice(1);
    return (hashFromUrl && validTabs.includes(hashFromUrl)) ? hashFromUrl : 'details';
  });
  
  // Set initial hash if not present
  useEffect(() => {
    const hashFromUrl = window.location.hash.slice(1);
    if (!hashFromUrl || !validTabs.includes(hashFromUrl)) {
      window.location.hash = activeTab;
    }
  }, []); // Only run on mount
  
  // Listen for hash changes (back/forward navigation)
  useEffect(() => {
    const handleHashChange = () => {
      const hashFromUrl = window.location.hash.slice(1);
      const tab = (hashFromUrl && validTabs.includes(hashFromUrl)) ? hashFromUrl : 'details';
      setActiveTab(tab);
    };
    
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);
  
  // Handler to update tab in URL hash
  const handleTabChange = (value: string) => {
    window.location.hash = value;
    setActiveTab(value);
  };

  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);

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
    },
  });

  const watchEnabled = form.watch('enabled');
  const isDirty = form.formState.isDirty;

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
        });
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
        });
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
        });
      }
    } catch (error) {
      console.error(`Error ${isNew ? 'creating' : 'updating'} MCP server:`, error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || `Failed to ${isNew ? 'create' : 'update'} MCP server. Please try again.`);
    } finally {
      setSaving(false);
    }
  };

  // Show save button for new servers or when form is dirty
  const showSaveButton = isNew || isDirty;

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
          onSave={form.handleSubmit(onSubmit)}
        />

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="details">Details</TabsTrigger>
                <TabsTrigger value="connection">Connection</TabsTrigger>
                <TabsTrigger value="tools" disabled>Tools</TabsTrigger>
              </TabsList>

              <TabsContent value="details" className="space-y-4">
                <DetailsTab form={form} isNew={isNew} />
              </TabsContent>

              <TabsContent value="connection" className="space-y-4">
                <ConnectionTab form={form} />
              </TabsContent>

              <TabsContent value="tools" className="space-y-4">
                <div className="text-center py-12 text-muted-foreground">
                  Tools tab coming soon
                </div>
              </TabsContent>
            </Tabs>
          </form>
        </Form>
      </div>
    </div>
  );
}
