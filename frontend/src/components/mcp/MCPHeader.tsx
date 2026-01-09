import { Save, Server } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { UseFormReturn } from 'react-hook-form';
import type { MCPFormValues } from './types';

interface MCPHeaderProps {
  form: UseFormReturn<MCPFormValues>;
  watchEnabled: boolean;
  isNew: boolean;
  showSaveButton: boolean;
  saving: boolean;
  onSave: () => void;
}

export function MCPHeader({
  form,
  watchEnabled,
  isNew,
  showSaveButton,
  saving,
  onSave,
}: MCPHeaderProps) {
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
            <h1 className="text-2xl font-bold">
              {form.watch('server_name') || 'MCP Server'}
            </h1>
          )}
          <Badge variant={watchEnabled ? 'default' : 'secondary'}>
            {watchEnabled ? 'Enabled' : 'Disabled'}
          </Badge>
          <Badge variant="outline">
            <Server className="w-3 h-3 mr-1" />
            MCP Server
          </Badge>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {showSaveButton && (
          <Button size="sm" onClick={onSave} disabled={saving}>
            <Save className="w-4 h-4 mr-2" />
            {saving ? (isNew ? 'Creating...' : 'Saving...') : (isNew ? 'Create' : 'Save')}
          </Button>
        )}
      </div>
    </div>
  );
}

