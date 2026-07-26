import { useEffect, useRef, useState } from 'react';
import { useFieldArray } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { UseFormReturn } from 'react-hook-form';
import { ChevronDown, Plus, Trash2 } from 'lucide-react';
import type { MCPFormValues } from './types';
import { mcpAuthTypes, mcpAuthHeaderNames, mcpTransportTypes, type MCPAuthType } from '@/data/mcp';
import {
  resolveAndStartMCPOAuthFlow,
  disconnectMCPOAuth,
  getMCPOAuthStatus,
} from '@/services/mcpApi';
import { toast } from 'sonner';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { BadgeVariant } from '@/utils/status';

function getOAuthStatusVariant(status?: string): BadgeVariant {
  if (status === 'Connected') return 'success';
  if (status === 'Token Expired') return 'destructive';
  return 'outline';
}

const credentialLabels: Partial<Record<MCPAuthType, string>> = {
  api_key: 'API Key',
  bearer_token: 'Token',
  custom_header: 'Header Value',
};

interface ConnectionTabProps {
  form: UseFormReturn<MCPFormValues>;
  serverName: string;
  isNew: boolean;
  onSaveAndConnect?: () => Promise<string | undefined>;
}

export function ConnectionTab({ form, serverName, isNew, onSaveAndConnect }: ConnectionTabProps) {
  const watchAuthType = form.watch('auth_type');
  const watchOAuthStatus = form.watch('oauth_status');
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showManualOAuth, setShowManualOAuth] = useState(false);

  const popupRef = useRef<Window | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'custom_headers',
  });

  // Clean up any lingering status poll when this tab unmounts.
  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  // Auto-fill auth_header_name based on auth_type
  useEffect(() => {
    if (watchAuthType && watchAuthType !== 'none' && watchAuthType !== 'oauth') {
      const headerName = mcpAuthHeaderNames[watchAuthType];
      if (headerName !== undefined) {
        form.setValue('auth_header_name', headerName, { shouldDirty: false });
      }
    } else if (watchAuthType === 'none' || watchAuthType === 'oauth') {
      // Clear auth fields when auth_type is 'none' or 'oauth'
      form.setValue('auth_header_name', '', { shouldDirty: false });
      form.setValue('auth_header_value', '', { shouldDirty: false });
    }
  }, [watchAuthType, form]);

  const showAuthFields = watchAuthType && watchAuthType !== 'none' && watchAuthType !== 'oauth';
  const isOAuthConnected = watchOAuthStatus === 'Connected';
  const canConnectOAuth = watchAuthType === 'oauth' || isNew;

  const handleConnectOAuth = async () => {
    setConnecting(true);

    let nameToUse = serverName;
    try {
      if (isNew) {
        if (!onSaveAndConnect) {
          toast.error('Please save the MCP server before connecting OAuth');
          setConnecting(false);
          return;
        }
        const savedName = await onSaveAndConnect();
        if (!savedName) {
          // Save-and-link path completed without starting OAuth (e.g. from-agent flow)
          setConnecting(false);
          return;
        }
        nameToUse = savedName;
      } else if (!serverName) {
        toast.error('Please save the MCP server before connecting OAuth');
        setConnecting(false);
        return;
      }

      // URL-first: backend discovers endpoints and registers client automatically.
      const result = await resolveAndStartMCPOAuthFlow(nameToUse);
      if (result.error) {
        toast.error(result.error);
        setConnecting(false);
        return;
      }
      if (!result.auth_url) {
        toast.error('Could not start OAuth flow.');
        setConnecting(false);
        return;
      }

      const popup = window.open(result.auth_url, '_blank', 'width=600,height=700');
      if (!popup) {
        toast.error('Popup blocked. Please allow popups for this site.');
        setConnecting(false);
        return;
      }
      popupRef.current = popup;

      if (pollRef.current) {
        clearInterval(pollRef.current);
      }
      pollRef.current = setInterval(async () => {
        if (!popup || popup.closed) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          try {
            const statusResult = await getMCPOAuthStatus(nameToUse);
            const status = statusResult.status || 'Not Connected';
            form.setValue('oauth_status', status, { shouldDirty: false });
          } catch (error) {
            console.error('Error fetching OAuth status:', error);
          } finally {
            setConnecting(false);
          }
        }
      }, 1000);
    } catch (error) {
      console.error('Error starting OAuth flow:', error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || 'Failed to start OAuth flow');
      setConnecting(false);
    }
  };

  const handleDisconnectOAuth = async () => {
    if (isNew || !serverName) {
      return;
    }

    if (!window.confirm('Disconnect this MCP Server from OAuth? Tokens will be deleted.')) {
      return;
    }

    setDisconnecting(true);
    try {
      const result = await disconnectMCPOAuth(serverName);
      if (result.success) {
        form.setValue('oauth_status', 'Not Connected', { shouldDirty: false });
        toast.success('Disconnected successfully');
      } else {
        toast.error(result.error || 'Failed to disconnect');
      }
    } catch (error) {
      console.error('Error disconnecting OAuth:', error);
      const errorMessage = getFrappeErrorMessage(error);
      toast.error(errorMessage || 'Failed to disconnect');
    } finally {
      setDisconnecting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* URL-first primary card */}
      <Card>
        <CardHeader>
          <CardTitle>MCP Server URL</CardTitle>
          <CardDescription>
            Paste the MCP endpoint and click Connect. HUF discovers OAuth settings and registers automatically.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <FormField
            control={form.control}
            name="server_url"
            render={({ field }) => (
              <FormItem>
                <FormControl>
                  <Input
                    placeholder="https://mcp.example.com/mcp"
                    {...field}
                  />
                </FormControl>
                <FormDescription>e.g. https://mcp.higgsfield.ai/mcp</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-lg border p-4">
            <div className="space-y-0.5">
              <p className="text-sm font-medium">Connection Status</p>
              <Badge variant={getOAuthStatusVariant(watchOAuthStatus)}>
                {watchOAuthStatus || 'Not Connected'}
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              {canConnectOAuth && !isOAuthConnected && (
                <Button
                  type="button"
                  onClick={handleConnectOAuth}
                  disabled={connecting || (isNew && !onSaveAndConnect)}
                >
                  {connecting ? 'Connecting…' : isNew ? 'Save & Connect' : 'Connect'}
                </Button>
              )}
              {isOAuthConnected && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleDisconnectOAuth}
                  disabled={disconnecting || isNew}
                >
                  {disconnecting ? 'Disconnecting…' : 'Disconnect'}
                </Button>
              )}
            </div>
          </div>

          {form.watch('oauth_discovery_status') && form.watch('oauth_discovery_status') !== 'Not Started' && (
            <div className="rounded-lg border p-4">
              <p className="text-sm font-medium">Discovery Status</p>
              <p className="text-sm text-muted-foreground">
                {form.watch('oauth_discovery_status')}
                {form.watch('oauth_authorization_server') && (
                  <> · Authorization server: {form.watch('oauth_authorization_server')}</>
                )}
                {form.watch('oauth_client_registration_method') && (
                  <> · Registration: {form.watch('oauth_client_registration_method')}</>
                )}
              </p>
              {form.watch('oauth_discovery_error') && (
                <p className="text-sm text-destructive mt-1">
                  {form.watch('oauth_discovery_error')}
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Advanced settings — collapsed by default */}
      <Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
        <Card>
          <CollapsibleTrigger asChild>
            <CardHeader className="cursor-pointer select-none">
              <div className="flex items-center justify-between gap-4">
                <div className="space-y-1.5">
                  <CardTitle className="text-base">Advanced Settings</CardTitle>
                  <CardDescription>
                    Authentication mode, transport, and custom headers. Usually not needed.
                  </CardDescription>
                </div>
                <ChevronDown
                  className={`h-5 w-5 shrink-0 text-muted-foreground transition-transform ${showAdvanced ? 'rotate-180' : ''}`}
                />
              </div>
            </CardHeader>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <CardContent className="grid gap-6">
              <FormField
                control={form.control}
                name="auth_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Authentication Mode</FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      value={field.value || 'none'}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select authentication mode" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {mcpAuthTypes.map((authType) => (
                          <SelectItem key={authType.value} value={authType.value}>
                            {authType.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>Leave as OAuth 2.1 for automatic discovery; switch only if the server requires a different mode</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {showAuthFields && (
                <>
                  {watchAuthType === 'custom_header' && (
                    <FormField
                      control={form.control}
                      name="auth_header_name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Header Name</FormLabel>
                          <FormControl>
                            <Input
                              placeholder="Authorization"
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}

                  <FormField
                    control={form.control}
                    name="auth_header_value"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{credentialLabels[watchAuthType as MCPAuthType] || 'Credential'}</FormLabel>
                        <FormControl>
                          <Input
                            type="password"
                            placeholder="Enter API key, bearer token, or header value"
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </>
              )}

              <FormField
                control={form.control}
                name="transport_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Transport Type</FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      value={field.value}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select transport type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {mcpTransportTypes.map((transportType) => (
                          <SelectItem key={transportType.value} value={transportType.value}>
                            {transportType.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>Leave as HTTP unless connecting to a legacy SSE-only server</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="border-t pt-6">
                <h4 className="text-sm font-medium mb-2">Custom Headers</h4>
                {fields.length === 0 ? (
                  <p className="text-sm text-muted-foreground mb-4">No custom headers configured.</p>
                ) : (
                  <div className="space-y-4 mb-4">
                    {fields.map((field, index) => (
                      <div key={field.id} className="grid gap-4 rounded-lg border p-4 md:grid-cols-[1fr_1fr_auto]">
                        <FormField
                          control={form.control}
                          name={`custom_headers.${index}.header_name`}
                          render={({ field: f }) => (
                            <FormItem>
                              <FormLabel>Header Name</FormLabel>
                              <FormControl>
                                <Input {...f} placeholder="X-Custom-Header" />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name={`custom_headers.${index}.header_value`}
                          render={({ field: f }) => (
                            <FormItem>
                              <FormLabel>Header Value</FormLabel>
                              <FormControl>
                                <Input {...f} placeholder="Header value" />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <div className="flex items-end">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            onClick={() => remove(index)}
                            className="text-destructive hover:text-destructive"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => append({ header_name: '', header_value: '' })}
                >
                  <Plus className="w-4 h-4 mr-2" />
                  Add Header
                </Button>
              </div>

              {watchAuthType === 'oauth' && (
                <div className="rounded-lg border">
                  <Collapsible open={showManualOAuth} onOpenChange={setShowManualOAuth}>
                    <CollapsibleTrigger asChild>
                      <button
                        type="button"
                        className="flex w-full items-center justify-between gap-4 p-4 text-left"
                      >
                        <div className="space-y-0.5">
                          <p className="text-sm font-medium">Manual OAuth Fallback</p>
                          <p className="text-sm text-muted-foreground">
                            Only for servers without automatic discovery or client registration.
                          </p>
                        </div>
                        <ChevronDown
                          className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${showManualOAuth ? 'rotate-180' : ''}`}
                        />
                      </button>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <div className="grid gap-6 border-t p-4">
                        <FormField
                          control={form.control}
                          name="oauth_client_id"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Client ID</FormLabel>
                              <FormControl>
                                <Input placeholder="Client ID" {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="oauth_client_secret"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Client Secret</FormLabel>
                              <FormControl>
                                <Input
                                  type="password"
                                  placeholder="Leave blank if using PKCE-only public client"
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="oauth_authorization_endpoint"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Authorization Endpoint</FormLabel>
                              <FormControl>
                                <Input
                                  placeholder="https://provider.example.com/oauth/authorize"
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="oauth_token_endpoint"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Token Endpoint</FormLabel>
                              <FormControl>
                                <Input
                                  placeholder="https://provider.example.com/oauth/token"
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="oauth_scope"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>OAuth Scope</FormLabel>
                              <FormControl>
                                <Textarea
                                  placeholder="read write"
                                  className="min-h-[80px] resize-y"
                                  {...field}
                                />
                              </FormControl>
                              <FormDescription>Space-separated OAuth scopes. Leave blank for provider default.</FormDescription>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="oauth_extra_authorize_params"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Extra Authorize Params (JSON)</FormLabel>
                              <FormControl>
                                <Textarea
                                  placeholder='{"access_type": "offline"}'
                                  className="min-h-[80px] resize-y"
                                  {...field}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />

                        <FormField
                          control={form.control}
                          name="oauth_redirect_uri"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Custom Redirect URI</FormLabel>
                              <FormControl>
                                <Input
                                  placeholder="https://provider.example.com/mcp-oauth-callback"
                                  {...field}
                                />
                              </FormControl>
                              <FormDescription>Optional: override the auto-generated callback URL</FormDescription>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>
                    </CollapsibleContent>
                  </Collapsible>
                </div>
              )}
            </CardContent>
          </CollapsibleContent>
        </Card>
      </Collapsible>
    </div>
  );
}
