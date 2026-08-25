import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { CodeBlock, CodeBlockCopyButton } from '@/components/ai-elements/code-block';
import {
  buildSnippet,
  buildLoginSnippet,
  type AuthMode,
  type SnippetLanguage,
  type SnippetRequest,
} from '@/lib/apiSnippets';

interface AgentApiDocsProps {
  baseUrl: string;
}

interface EndpointDoc {
  request: SnippetRequest;
  description: string;
}

const ENDPOINTS: EndpointDoc[] = [
  {
    request: { method: 'GET', path: '/agents' },
    description: 'List every agent your key is permitted to use.',
  },
  {
    request: { method: 'GET', path: '/agents/{agent_id}' },
    description: "Get a single agent's public details.",
  },
  {
    request: {
      method: 'POST',
      path: '/responses',
      body: { agent_id: 'Demo Assistant', input: 'Hello!' },
    },
    description: 'Run an agent with a message. Requires the "agents:run" permission.',
  },
];

const LANGUAGES: { value: SnippetLanguage; label: string }[] = [
  { value: 'curl', label: 'curl' },
  { value: 'python', label: 'Python' },
  { value: 'javascript', label: 'JavaScript' },
  { value: 'typescript', label: 'TypeScript' },
];

const CODE_BLOCK_LANGUAGE: Record<SnippetLanguage, string> = {
  curl: 'bash',
  python: 'python',
  javascript: 'javascript',
  typescript: 'typescript',
};

export function AgentApiDocs({ baseUrl }: AgentApiDocsProps) {
  const [language, setLanguage] = useState<SnippetLanguage>('curl');
  const [authMode, setAuthMode] = useState<AuthMode>('apiKey');

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agent API</CardTitle>
        <CardDescription>
          List, inspect, and run agents from your own code.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <ToggleGroup
            type="single"
            value={authMode}
            onValueChange={(value) => value && setAuthMode(value as AuthMode)}
            className="justify-start"
          >
            <ToggleGroupItem value="apiKey" className="text-xs">
              API key
            </ToggleGroupItem>
            <ToggleGroupItem value="session" className="text-xs">
              Session
            </ToggleGroupItem>
          </ToggleGroup>

          <Tabs value={language} onValueChange={(value) => setLanguage(value as SnippetLanguage)}>
            <TabsList>
              {LANGUAGES.map((lang) => (
                <TabsTrigger key={lang.value} value={lang.value} className="text-xs">
                  {lang.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        {authMode === 'apiKey' ? (
          <p className="text-sm text-muted-foreground">
            Requests are authenticated with a key from API Keys below, sent as the{' '}
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">X-Huf-Api-Key</code> header.
          </p>
        ) : (
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Session auth uses the cookie from logging in — log in first to get a session, then reuse it
              for subsequent requests:
            </p>
            <CodeBlock code={buildLoginSnippet(baseUrl, language)} language={CODE_BLOCK_LANGUAGE[language]}>
              <CodeBlockCopyButton />
            </CodeBlock>
          </div>
        )}

        {ENDPOINTS.map((endpoint) => (
          <div key={`${endpoint.request.method}-${endpoint.request.path}`} className="space-y-2">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="font-mono text-xs">
                {endpoint.request.method}
              </Badge>
              <code className="text-sm font-mono">{endpoint.request.path}</code>
            </div>
            <p className="text-sm text-muted-foreground">{endpoint.description}</p>
            <CodeBlock
              code={buildSnippet(baseUrl, endpoint.request, language, authMode)}
              language={CODE_BLOCK_LANGUAGE[language]}
            >
              <CodeBlockCopyButton />
            </CodeBlock>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
