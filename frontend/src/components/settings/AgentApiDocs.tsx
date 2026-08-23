import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CodeBlock, CodeBlockCopyButton } from '@/components/ai-elements/code-block';

interface AgentApiDocsProps {
  baseUrl: string;
}

interface EndpointDoc {
  method: string;
  path: string;
  description: string;
  example: string;
}

function buildEndpoints(baseUrl: string): EndpointDoc[] {
  return [
    {
      method: 'GET',
      path: '/agents',
      description: 'List every agent your key is permitted to use.',
      example: `curl "${baseUrl}/agents" \\
  -H "X-Huf-Api-Key: huf_sk_..."`,
    },
    {
      method: 'GET',
      path: '/agents/{agent_id}',
      description: 'Get a single agent\'s public details.',
      example: `curl "${baseUrl}/agents/Demo Assistant" \\
  -H "X-Huf-Api-Key: huf_sk_..."`,
    },
    {
      method: 'POST',
      path: '/responses',
      description: 'Run an agent with a message. Requires the "agents:run" permission.',
      example: `curl -X POST "${baseUrl}/responses" \\
  -H "X-Huf-Api-Key: huf_sk_..." \\
  -d "agent_id=Demo Assistant" \\
  -d "input=Hello!"`,
    },
  ];
}

export function AgentApiDocs({ baseUrl }: AgentApiDocsProps) {
  const endpoints = buildEndpoints(baseUrl);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Agent API</CardTitle>
        <CardDescription>
          List, inspect, and run agents from your own code. Every request needs a key from API Keys
          below, sent as the <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">X-Huf-Api-Key</code> header.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {endpoints.map((endpoint) => (
          <div key={`${endpoint.method}-${endpoint.path}`} className="space-y-2">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="font-mono text-xs">
                {endpoint.method}
              </Badge>
              <code className="text-sm font-mono">{endpoint.path}</code>
            </div>
            <p className="text-sm text-muted-foreground">{endpoint.description}</p>
            <CodeBlock code={endpoint.example} language="bash">
              <CodeBlockCopyButton />
            </CodeBlock>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
