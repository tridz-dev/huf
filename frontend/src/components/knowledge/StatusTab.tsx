import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { AlertCircle } from 'lucide-react';
import { formatTimeAgo } from '@/utils/time';
import type { KnowledgeSourceDoc } from '@/types/knowledge.types';

interface StatusTabProps {
  source: KnowledgeSourceDoc | null;
}

function getStatusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'Ready':
      return 'default';
    case 'Indexing':
    case 'Rebuilding':
      return 'outline';
    case 'Error':
      return 'destructive';
    default:
      return 'secondary';
  }
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function StatusTab({ source }: StatusTabProps) {
  if (!source) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          Save the knowledge source first to see status information.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {source.status === 'Error' && source.error_message && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Indexing Error</AlertTitle>
          <AlertDescription className="mt-2 whitespace-pre-wrap">
            {source.error_message}
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Index Status</CardTitle>
          <CardDescription>Current state of the knowledge source index</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-6 sm:grid-cols-2">
            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Status</p>
              <Badge variant={getStatusVariant(source.status)}>{source.status}</Badge>
            </div>

            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Last Indexed</p>
              <p className="text-sm">
                {source.last_indexed_at ? formatTimeAgo(source.last_indexed_at) : 'Never'}
              </p>
            </div>

            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Total Chunks</p>
              <p className="text-sm">{source.total_chunks.toLocaleString()}</p>
            </div>

            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Total Inputs</p>
              <p className="text-sm">{source.total_inputs.toLocaleString()}</p>
            </div>

            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">Index Size</p>
              <p className="text-sm">{formatBytes(source.index_size_bytes)}</p>
            </div>

            {source.sqlite_file_path && (
              <div className="space-y-1">
                <p className="text-sm font-medium text-muted-foreground">SQLite File</p>
                <p className="text-sm font-mono text-xs break-all">{source.sqlite_file_path}</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
