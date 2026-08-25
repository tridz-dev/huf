import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { CreateApiKeyDialog } from '@/components/settings/CreateApiKeyDialog';
import { ApiKeyCreatedDialog } from '@/components/settings/ApiKeyCreatedDialog';
import {
  listApiKeys,
  revokeApiKey,
  type ApiKey,
  type CreatedApiKey,
} from '@/services/developerApi';
import { handleFrappeError } from '@/lib/frappe-error';

function formatDate(value: string | null): string {
  if (!value) {
    return '-';
  }
  return new Date(value).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function maskKeyId(keyId: string): string {
  if (keyId.length <= 8) {
    return keyId;
  }
  return `${keyId.slice(0, 4)}...${keyId.slice(-4)}`;
}

function statusVariant(status: string): 'success' | 'destructive' | 'secondary' {
  const normalized = status.toLowerCase();
  if (normalized === 'active') {
    return 'success';
  }
  if (normalized === 'revoked' || normalized === 'expired') {
    return 'destructive';
  }
  return 'secondary';
}

export function ApiKeysSection() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [createdKey, setCreatedKey] = useState<CreatedApiKey | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<ApiKey | null>(null);
  const [revoking, setRevoking] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const result = await listApiKeys();
      setKeys(result);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleCreated = (key: CreatedApiKey) => {
    setCreateOpen(false);
    setCreatedKey(key);
    refresh();
  };

  const handleRevoke = async () => {
    if (!revokeTarget) {
      return;
    }
    setRevoking(true);
    try {
      const result = await revokeApiKey(revokeTarget.key_id);
      if (result) {
        toast.success('Key revoked');
        setRevokeTarget(null);
        refresh();
      }
    } catch (error) {
      handleFrappeError(error, 'Error revoking API key');
    } finally {
      setRevoking(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle>API Keys</CardTitle>
          <CardDescription>
            Keys used to access HUF programmatically.
          </CardDescription>
        </div>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-1" />
          Create key
        </Button>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : keys.length === 0 ? (
          <p className="text-sm text-muted-foreground">No API keys yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Key</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Permissions</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Last used</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((key) => (
                <TableRow key={key.key_id}>
                  <TableCell className="font-medium">{key.label}</TableCell>
                  <TableCell className="font-mono text-xs">{maskKeyId(key.key_id)}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(key.status)}>{key.status}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {key.scopes.map((scope) => (
                        <Badge key={scope} variant="outline">{scope}</Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>{formatDate(key.creation)}</TableCell>
                  <TableCell>{formatDate(key.last_used_at)}</TableCell>
                  <TableCell>{key.expires_at ? formatDate(key.expires_at) : 'Never'}</TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={key.status.toLowerCase() !== 'active'}
                      onClick={() => setRevokeTarget(key)}
                    >
                      Revoke
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>

      <CreateApiKeyDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={handleCreated}
      />

      <ApiKeyCreatedDialog apiKey={createdKey} onClose={() => setCreatedKey(null)} />

      <AlertDialog open={!!revokeTarget} onOpenChange={(next) => { if (!revoking && !next) setRevokeTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke "{revokeTarget?.label}"?</AlertDialogTitle>
            <AlertDialogDescription>
              Any integration using this key will immediately lose access. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={revoking}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRevoke}
              disabled={revoking}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {revoking ? 'Revoking...' : 'Revoke'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
