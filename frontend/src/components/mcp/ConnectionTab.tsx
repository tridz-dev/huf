import { useEffect, useState } from 'react';
import { useFieldArray } from 'react-hook-form';
import { FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { UseFormReturn } from 'react-hook-form';
import { Plus, Trash2 } from 'lucide-react';
import type { MCPFormValues } from './types';
import { mcpAuthTypes, mcpAuthHeaderNames, mcpTransportTypes } from '@/data/mcp';
import {
  startMCPOAuthFlow,
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

interface ConnectionTabProps {
  form: UseFormReturn<MCPFormValues>;
  serverName: string;
  isNew: boolean;
}

export function ConnectionTab({ form, serverName, isNew }: ConnectionTabProps) {
  const watchAuthType = form.watch('auth_type');
  const watchOAuthStatus = form.watch('oauth_status');
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'custom_headers',
  });

  // Auto-fill auth_header_name based on auth_type
  useEffect(() => {
    if (watchAuthType && watchAuthType !== 'none') {
      const headerName = mcpAuthHeaderNames[watchAuthType];
      if (headerName !== undefined) {
        form.setValue('auth_header_name', headerName, { shouldDirty: false });
      }
    } else if (watchAuthType === 'none') {
      // Clear auth fields when auth_type is 'none'
      form.setValue('auth_header_name', '', { shouldDirty: false });
      form.setValue('auth_header_value', '', { shouldDirty: false });
    }
  }, [watchAuthType, form]);

  const showAuthFields = watchAuthType && watchAuthType !== 'none';
  const showOAuthFields = watchAuthType === 'oauth';
  const isOAuthConnected = watchOAuthStatus === 'Connected';

  const handleConnectOAuth = async () => {
    if (isNew || !serverName) {
      toast.error('Please save the MCP server before connecting OAuth');
      return;
    }

    const values = form.getValues();
    if (!values.oauth_authorization_endpoint || !values.oauth_token_endpoint || !values.oauth_client_id) {
      toast.error('Please fill in Authorization Endpoint, Token Endpoint, and Client ID before connecting.');
      return;
    }

    setConnecting(true);
    try {
      const result = await startMCPOAuthFlow(serverName);
      if (result.error) {
        toast.error(result.error);
        return;
      }
      if (!result.auth_url) {
        toast.error('Could not start OAuth flow.');
        return;
      }

      const popup = window.open(result.auth_url, '_blank', 'width=600,height=700');
      if (!popup) {
        toast.error('Popup blocked. Please allow popups for this site.');
        return;
      }

      const poll = setInterval(async () => {
        if (!popup || popup.closed) {
          clearInterval(poll);
          try {
            const statusResult = await getMCPOAuthStatus(serverName);
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
      <Card>
        <CardHeader>
          <CardTitle>Connection Settings</CardTitle>
          <CardDescription>Configure authentication and connection parameters</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
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
                <FormDescription>Communication protocol for MCP server</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="server_url"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Server URL</FormLabel>
                <FormControl>
                  <Input
                    placeholder="https://mcp.example.com/mcp"
                    {...field}
                  />
                </FormControl>
                <FormDescription>MCP server endpoint URL (e.g., 'https://mcp.example.com/mcp')</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="auth_type"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Authentication Type</FormLabel>
                <Select
                  onValueChange={field.onChange}
                  value={field.value || 'none'}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select authentication type" />
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
                <FormDescription>Select the authentication method for this MCP server</FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          {showAuthFields && (
            <>
              <FormField
                control={form.control}
                name="auth_header_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Auth Header Name</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="Authorization"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      Header name for authentication (e.g., &apos;Authorization&apos;, &apos;X-API-Key&apos;)
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="auth_header_value"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Auth Header Value</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder="Enter API key, bearer token, or header value"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>The API key, bearer token, or header value (stored encrypted)</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </>
          )}
        </CardContent>
      </Card>

      {showOAuthFields && (
        <Card>
          <CardHeader>
            <CardTitle>OAuth 2.1 Configuration</CardTitle>
            <CardDescription>Configure OAuth endpoints and connect the server</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6">
            <div className="flex flex-row items-center justify-between rounded-none border p-4">
              <div className="space-y-0.5">
                <p className="text-sm font-medium">OAuth Status</p>
                <Badge variant={getOAuthStatusVariant(watchOAuthStatus)}>
                  {watchOAuthStatus || 'Not Connected'}
                </Badge>
              </div>
              <div className="flex items-center gap-2">
                {!isOAuthConnected && (
                  <Button
                    type="button"
                    onClick={handleConnectOAuth}
                    disabled={connecting || isNew}
                  >
                    {connecting ? 'Connecting…' : 'Connect'}
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
                  <FormDescription>Space-separated OAuth scopes (e.g. &apos;read write&apos;). Leave blank for provider default.</FormDescription>
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
                  <FormDescription>Additional URL parameters for the authorization endpoint (e.g. {`{"user_scope": "...", "access_type": "offline"}`})</FormDescription>
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
                  <FormDescription>
                    Optional: Override the callback URL for strict providers or local testing. Leave blank to use HUF&apos;s default: {'{site_url}'}/mcp-oauth-callback.
                  </FormDescription>
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
                  <FormDescription>e.g. https://higgsfield.ai/oauth/authorize</FormDescription>
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
                  <FormDescription>e.g. https://higgsfield.ai/oauth/token</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

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
                  <FormDescription>Stored encrypted. Leave blank if using PKCE-only public client.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="oauth_token_response_path"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Token Response Path</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="access_token"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>JSON path to access token if nested (e.g. authed_user.access_token). Defaults to access_token.</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Custom Headers</CardTitle>
          <CardDescription>Additional HTTP headers to send with MCP requests</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          {fields.length === 0 ? (
            <p className="text-sm font-body text-steel-soft">No custom headers configured.</p>
          ) : (
            <div className="space-y-4">
              {fields.map((field, index) => (
                <div key={field.id} className="grid gap-4 rounded-none border p-4 md:grid-cols-[1fr_1fr_auto]">
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
        </CardContent>
      </Card>
    </div>
  );
}
