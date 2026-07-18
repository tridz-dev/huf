import { Save, Server, RefreshCw, Wifi, MoreVertical, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { UseFormReturn } from 'react-hook-form';
import { cn } from '@/lib/utils';
import type { MCPFormValues } from './types';
import { InlineEditName } from '@/components/common/InlineEditName';

interface MCPHeaderProps {
  form: UseFormReturn<MCPFormValues>;
  watchEnabled: boolean;
  isNew: boolean;
  showSaveButton: boolean;
  saving: boolean;
  syncing?: boolean;
  testingConnection?: boolean;
  fromAgent?: string;
  onSave: () => void;
  onCancel?: () => void;
  onSync?: () => void;
  onTestConnection?: () => void;
  onDelete?: () => void;
}

export function MCPHeader({
  form,
  watchEnabled,
  isNew,
  showSaveButton,
  saving,
  syncing = false,
  testingConnection = false,
  fromAgent,
  onSave,
  onCancel,
  onSync,
  onTestConnection,
  onDelete,
}: MCPHeaderProps) {
  const watchAuthType = form.watch('auth_type');
  const watchOAuthStatus = form.watch('oauth_status');
  const isOAuthConnected = watchAuthType === 'oauth' && watchOAuthStatus === 'Connected';

  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
      <div className="flex-1 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          {isNew ? (
            <Input
              value={form.watch('server_name') || ''}
              onChange={(e) => form.setValue('server_name', e.target.value, { shouldDirty: true })}
              className="text-2xl font-bold h-auto border-0 px-0 focus-visible:ring-0 max-w-md"
              placeholder="MCP Server Name"
            />
          ) : (
            <InlineEditName
              value={form.watch('server_name') || ''}
              onChange={(value) => form.setValue('server_name', value, { shouldDirty: true })}
              placeholder="MCP Server Name"
            />
          )}
          <Badge variant={watchEnabled ? 'success' : 'secondary'}>
            {watchEnabled ? 'Enabled' : 'Disabled'}
          </Badge>
          {isOAuthConnected && (
            <Badge variant="success">Connected</Badge>
          )}
          <Badge variant="outline">
            <Server className="w-3 h-3 mr-1" />
            MCP Server
          </Badge>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {fromAgent && onCancel && (
          <Button
            size="sm"
            variant="outline"
            onClick={onCancel}
            type="button"
            disabled={saving || syncing || testingConnection}
          >
            Cancel
          </Button>
        )}
        {!isNew && onSync && (
          <Button
            variant="outline"
            size="sm"
            onClick={onSync}
            disabled={syncing || saving || testingConnection}
            type="button"
            title={syncing ? 'Syncing tools...' : 'Sync tools from MCP server'}
          >
            <RefreshCw className={cn('w-4 h-4 mr-2', syncing && 'animate-spin')} />
            {syncing ? 'Syncing...' : 'Sync Now'}
          </Button>
        )}
        {!isNew && onTestConnection && (
          <Button
            variant="outline"
            size="sm"
            onClick={onTestConnection}
            disabled={testingConnection || saving || syncing}
            type="button"
            title={testingConnection ? 'Testing connection...' : 'Test connection to MCP server'}
          >
            <Wifi className={cn('w-4 h-4 mr-2', testingConnection && 'animate-pulse')} />
            {testingConnection ? 'Testing...' : 'Test Connection'}
          </Button>
        )}
        {showSaveButton && (
          <Button size="sm" onClick={onSave} disabled={saving || syncing || testingConnection}>
            <Save className="w-4 h-4 mr-2" />
            {saving ? (isNew ? 'Creating...' : 'Saving...') : (isNew ? 'Create' : 'Save')}
          </Button>
        )}
        {!isNew && onDelete && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" type="button">
                <MoreVertical className="w-4 h-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onDelete} className="text-destructive">
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </div>
  );
}

