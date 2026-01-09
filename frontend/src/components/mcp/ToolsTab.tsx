import { useState } from 'react';
import { FormField, FormItem, FormLabel, FormControl, FormDescription } from '@/components/ui/form';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { UseFormReturn } from 'react-hook-form';
import type { MCPFormValues, MCPTool } from './types';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatTimeAgo } from '@/utils/time';
import { MCPToolDetailModal } from './MCPToolDetailModal';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ToolsTabProps {
  form: UseFormReturn<MCPFormValues>;
  tools: MCPTool[];
  lastSync?: string;
  onToolToggle: (toolName: string, enabled: boolean) => void;
  onSync: () => void;
  syncing: boolean;
}

export function ToolsTab({
  form,
  tools,
  lastSync,
  onToolToggle,
  onSync,
  syncing,
}: ToolsTabProps) {
  const [selectedTool, setSelectedTool] = useState<MCPTool | null>(null);

  const handleToolClick = (tool: MCPTool) => {
    setSelectedTool(tool);
  };

  const handleToolToggle = (toolName: string, enabled: boolean, e?: React.MouseEvent) => {
    e?.stopPropagation();
    onToolToggle(toolName, enabled);
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Sync Settings</CardTitle>
          <CardDescription>Configure tool synchronization settings</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6">
          <FormField
            control={form.control}
            name="enable_auto_sync"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Enable Auto Sync</FormLabel>
                  <FormDescription>
                    Automatically sync tools from the MCP server on a schedule
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch
                    checked={field.value || false}
                    onCheckedChange={field.onChange}
                  />
                </FormControl>
              </FormItem>
            )}
          />

          <div className="flex items-center justify-between p-4 rounded-lg border bg-muted/30">
            <div>
              <p className="text-sm font-medium">Last Sync</p>
              <p className="text-sm text-muted-foreground">{formatTimeAgo(lastSync)}</p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={onSync}
              disabled={syncing}
            >
              <RefreshCw className={cn('w-4 h-4 mr-2', syncing && 'animate-spin')} />
              {syncing ? 'Syncing...' : 'Sync Now'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Available Tools</CardTitle>
          <CardDescription>
            {tools.length > 0
              ? `${tools.length} tool${tools.length !== 1 ? 's' : ''} available`
              : 'No tools available. Sync tools to get started.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {tools.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <p>No tools available.</p>
              <Button
                variant="outline"
                size="sm"
                onClick={onSync}
                disabled={syncing}
                className="mt-4"
              >
                <RefreshCw className={cn('w-4 h-4 mr-2', syncing && 'animate-spin')} />
                {syncing ? 'Syncing...' : 'Sync Tools'}
              </Button>
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tool Name</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead className="text-right">Enabled</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tools.map((tool) => (
                    <TableRow
                      key={tool.name}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => handleToolClick(tool)}
                    >
                      <TableCell className="font-medium">{tool.tool_name}</TableCell>
                      <TableCell className="text-muted-foreground">
                        <div className="max-w-md truncate" title={tool.description || 'No description'}>
                          {tool.description || 'No description'}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <Switch
                          checked={tool.enabled === 1}
                          onCheckedChange={(enabled) => handleToolToggle(tool.name, enabled)}
                          onClick={(e: React.MouseEvent) => e.stopPropagation()}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {selectedTool && (
        <MCPToolDetailModal
          tool={selectedTool}
          open={!!selectedTool}
          onOpenChange={(open) => !open && setSelectedTool(null)}
          onToggle={(enabled) => {
            onToolToggle(selectedTool.name, enabled);
            setSelectedTool({ ...selectedTool, enabled: enabled ? 1 : 0 });
          }}
        />
      )}
    </div>
  );
}

