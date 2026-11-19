import { Alert, AlertDescription } from '@/components/ui/alert';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Link } from 'react-router-dom';
import type { ImportOptions } from '@/services/knowledgeApi';

import type { RemoteValues } from './importHelpers';

interface PanelProps {
  options: ImportOptions;
  values: RemoteValues;
  onChange: (next: RemoteValues) => void;
  disabled?: boolean;
}

export function DirectoryPanel({ options, values, onChange, disabled }: PanelProps) {
  const roots = options.directory_roots;
  return (
    <div className="space-y-3">
      <Alert>
        <AlertDescription>Visible to administrators only. Files are read from the server itself.</AlertDescription>
      </Alert>
      {roots.length > 1 && (
        <Field label="Allowed location">
          <Select value={values.dirPath} onValueChange={(v) => onChange({ ...values, dirPath: v })} disabled={disabled}>
            <SelectTrigger>
              <SelectValue placeholder="Choose a location" />
            </SelectTrigger>
            <SelectContent>
              {roots.map((r) => (
                <SelectItem key={r} value={r}>
                  {r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      )}
      <Field label="Folder path" hint={`Must be inside: ${roots.join(', ')}`}>
        <Input
          value={values.dirPath}
          onChange={(e) => onChange({ ...values, dirPath: e.target.value })}
          placeholder={roots[0] ?? '/path/to/folder'}
          disabled={disabled}
        />
      </Field>
    </div>
  );
}

export function S3Panel({ options, values, onChange, disabled }: PanelProps) {
  if (!options.s3_configured) {
    return (
      <Alert>
        <AlertDescription>
          Connect your S3 credentials in Integrations first, then come back to import from a bucket.{' '}
          <Link to="/integrations" className="text-signal-ink underline">
            Open Integrations
          </Link>
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <div className="space-y-3">
      <Field label="Bucket" required>
        <Input
          value={values.bucket}
          onChange={(e) => onChange({ ...values, bucket: e.target.value })}
          placeholder="my-bucket"
          disabled={disabled}
        />
      </Field>
      <Field label="Folder prefix (optional)" hint="Only files under this prefix are imported.">
        <Input
          value={values.prefix}
          onChange={(e) => onChange({ ...values, prefix: e.target.value })}
          placeholder="docs/"
          disabled={disabled}
        />
      </Field>
    </div>
  );
}

export function SftpPanel({ options, values, onChange, disabled }: PanelProps) {
  if (options.ssh_connections.length === 0) {
    return (
      <Alert>
        <AlertDescription>
          No SSH connections are available. Create an SSH Connection first, then come back to import from an SFTP server.
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <div className="space-y-3">
      <Field label="Connection" required>
        <Select
          value={values.sshConnection}
          onValueChange={(v) => onChange({ ...values, sshConnection: v })}
          disabled={disabled}
        >
          <SelectTrigger>
            <SelectValue placeholder="Choose a connection" />
          </SelectTrigger>
          <SelectContent>
            {options.ssh_connections.map((c) => (
              <SelectItem key={c.name} value={c.name}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Field label="Folder on the server" required>
        <Input
          value={values.rootPath}
          onChange={(e) => onChange({ ...values, rootPath: e.target.value })}
          placeholder="/docs"
          disabled={disabled}
        />
      </Field>
    </div>
  );
}
