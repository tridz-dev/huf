import { useEffect, useState } from 'react';
import { Check, Copy, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { copyText } from '@/lib/clipboard';
import type { ConnectionSnippets } from '@/types/external/agents.types';
import { getConnectionSnippets } from '@/services/external/agentsApi';

interface ConnectionSetupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  connection: string;
  agentName: string;
  /** True when the user has other connections, so the connection header must be sent too. */
  hasSiblings: boolean;
}

interface SnippetProps {
  id: string;
  title: string;
  description: string;
  text: string;
}

function buildSnippets(details: ConnectionSnippets, hasSiblings: boolean) {
  const { url, header_name: headerName, header_value_template: headerValue } = details;
  const authHeader = `${headerName}: ${headerValue}`;
  const connectionHeader = `${details.connection_header}: ${details.connection}`;

  const cliParts = [
    'claude mcp add --transport http huf',
    url,
    `--header "${authHeader}"`,
  ];
  if (hasSiblings) cliParts.push(`--header "${connectionHeader}"`);

  const desktopArgs = ['-y', 'mcp-remote', url, '--header', `${headerName}:\${HUF_AUTH}`];
  if (hasSiblings) desktopArgs.push('--header', `${details.connection_header}:\${HUF_CONNECTION}`);
  const desktopEnv: Record<string, string> = { HUF_AUTH: headerValue };
  if (hasSiblings) desktopEnv.HUF_CONNECTION = details.connection;
  const desktopConfig = {
    mcpServers: {
      huf: {
        command: 'npx',
        args: desktopArgs,
        env: desktopEnv,
      },
    },
  };

  return {
    cli: cliParts.join(' '),
    desktop: JSON.stringify(desktopConfig, null, 2),
    address: url,
  };
}

function Snippet({ id, title, description, text }: SnippetProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (await copyText(text)) {
      setCopied(true);
      toast.success('Copied');
      setTimeout(() => setCopied(false), 1500);
    } else {
      toast.error("Couldn't copy. Select the text and copy it yourself.");
    }
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-medium">{title}</h3>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void handleCopy()}>
          {copied ? <Check className="mr-2 h-3.5 w-3.5" /> : <Copy className="mr-2 h-3.5 w-3.5" />}
          Copy
        </Button>
      </div>
      <pre
        id={id}
        data-testid={id}
        className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-md border bg-muted p-3 font-mono text-xs"
      >
        {text}
      </pre>
    </div>
  );
}

export function ConnectionSetupDialog({
  open,
  onOpenChange,
  connection,
  agentName,
  hasSiblings,
}: ConnectionSetupDialogProps) {
  const [details, setDetails] = useState<ConnectionSnippets | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setIsLoading(true);
    setLoadFailed(false);
    getConnectionSnippets(connection)
      .then((result) => {
        if (!cancelled) setDetails(result);
      })
      .catch(() => {
        if (!cancelled) {
          setLoadFailed(true);
          toast.error("Couldn't load setup details. Please try again.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, connection]);

  const snippets = details ? buildSnippets(details, hasSiblings) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Set up {agentName}</DialogTitle>
          <DialogDescription>
            Copy one of these into your AI app to let it use Huf with your permissions.
          </DialogDescription>
        </DialogHeader>

        {isLoading && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading setup details...
          </p>
        )}

        {loadFailed && !isLoading && (
          <p className="text-sm text-destructive">Setup details are not available right now.</p>
        )}

        {snippets && details && (
          <div className="space-y-5">
            <p className="text-xs text-muted-foreground">
              Create an access key under your user settings, then replace <code>&lt;api_key&gt;</code>{' '}
              and <code>&lt;api_secret&gt;</code>.
            </p>

            <Snippet
              id="snippet-cli"
              title="Terminal AI app"
              description="Run this once in your terminal."
              text={snippets.cli}
            />
            <Snippet
              id="snippet-desktop"
              title="Desktop AI app"
              description="Add this to your app's settings file. Needs Node.js installed."
              text={snippets.desktop}
            />
            <Snippet
              id="snippet-url"
              title="Server address"
              description="Use this address when your app asks for a URL."
              text={snippets.address}
            />

            {hasSiblings && (
              <p className="text-xs text-muted-foreground">
                You have several connections. Keep the <code>{details.connection_header}</code> header
                set to <code>{details.connection}</code> so requests reach this one.
              </p>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
