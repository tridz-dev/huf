import { useMemo, useState } from 'react';
import { ArrowRight, Command, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { parseSlashCommand, type ParsedCommand } from '@/services/commandParser';

const starterPrompts = [
  '/flow create approval for todo',
  '/agent create support assistant for billing',
  '/users add teammate as builder in realm operations',
  '/runs retry failed since yesterday',
  '/cost show last 7 days by model',
];

const commandCatalog = [
  { domain: 'flow', hint: 'Create and manage automations', route: '/flows' },
  { domain: 'agent', hint: 'Build and manage agents', route: '/agents' },
  { domain: 'users', hint: 'Invite/remove users', route: '/users' },
  { domain: 'knowledge', hint: 'Index and query sources', route: '/knowledge' },
  { domain: 'runs', hint: 'Inspect and retry executions', route: '/executions' },
  { domain: 'cost', hint: 'Analyze usage and cost', route: '/executions' },
  { domain: 'realm', hint: 'Realm-level operations', route: '/users' },
] as const;

const domainRouteMap = Object.fromEntries(commandCatalog.map((item) => [item.domain, item.route]));

export { HomePage };
export default HomePage;

function HomePage() {
  const navigate = useNavigate();
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [lastParsed, setLastParsed] = useState<ParsedCommand | null>(null);

  const showCommandPicker = input.trim().startsWith('/');

  const filteredCatalog = useMemo(() => {
    if (!showCommandPicker) return commandCatalog;
    const needle = input.replace('/', '').trim().toLowerCase();
    if (!needle) return commandCatalog;
    return commandCatalog.filter((item) => item.domain.includes(needle) || item.hint.toLowerCase().includes(needle));
  }, [input, showCommandPicker]);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed) return;

    if (!trimmed.startsWith('/')) {
      navigate('/chat');
      return;
    }

    try {
      const parsed = parseSlashCommand(trimmed);
      setLastParsed(parsed);
      setError(null);

      const route = domainRouteMap[parsed.domain] ?? '/';
      navigate(route);
    } catch (parseError) {
      const message = parseError instanceof Error ? parseError.message : 'Unable to parse command.';
      setError(message);
      setLastParsed(null);
    }
  };

  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-6 md:p-10">
        <section className="rounded-2xl border bg-gradient-to-b from-muted/20 to-background p-6 md:p-10">
          <div className="mb-6 flex items-center gap-2 text-sm text-muted-foreground">
            <Sparkles className="h-4 w-4" />
            Hub Simple powered by Huf orchestrator
          </div>
          <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">What are you building today?</h1>
          <p className="mt-2 max-w-2xl text-muted-foreground">
            Use natural language or type <code>/</code> for a command. Commands route to focused sub-agents such as
            flow, users, and cost operations.
          </p>

          <div className="mt-6 flex flex-col gap-3 md:flex-row">
            <Input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  handleSubmit();
                }
              }}
              placeholder="Try: /flow create approval for todo"
              className="h-11"
            />
            <Button className="h-11 px-6" onClick={handleSubmit}>
              Run
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
            <Button variant="outline" className="h-11" onClick={() => navigate('/chat')}>
              Open Advanced Chat
            </Button>
          </div>

          {showCommandPicker && (
            <div className="mt-3 rounded-lg border bg-card p-3">
              <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                <Command className="h-4 w-4" />
                Command shortcuts
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                {filteredCatalog.map((item) => (
                  <button
                    key={item.domain}
                    className="rounded-md border bg-background px-3 py-2 text-left text-sm hover:bg-muted"
                    onClick={() => setInput(`/${item.domain} `)}
                    type="button"
                  >
                    <div className="font-medium">/{item.domain}</div>
                    <div className="text-xs text-muted-foreground">{item.hint}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

          {lastParsed && (
            <div className="mt-3 rounded-lg border bg-card p-3 text-sm">
              <div className="font-medium">Parsed command</div>
              <div className="mt-1 text-muted-foreground">
                {lastParsed.routingMode} → <strong>{lastParsed.domain}</strong> / {lastParsed.verb}
              </div>
            </div>
          )}
        </section>

        <section>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">Starter actions</h2>
          <div className="grid gap-3 md:grid-cols-2">
            {starterPrompts.map((prompt) => (
              <button
                key={prompt}
                className="rounded-lg border bg-card px-4 py-3 text-left text-sm hover:bg-muted"
                onClick={() => setInput(prompt)}
                type="button"
              >
                {prompt}
              </button>
            ))}
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Permissions</CardTitle>
              <CardDescription>Huf roles and agent-level controls are applied automatically.</CardDescription>
            </CardHeader>
            <CardContent>
              <Badge variant="secondary">No new privilege model</Badge>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Orchestration</CardTitle>
              <CardDescription>Requests are delegated to domain agents for clearer scope.</CardDescription>
            </CardHeader>
            <CardContent>
              <Badge variant="secondary">Orchestrator + Sub-agents</Badge>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Need full control?</CardTitle>
              <CardDescription>Switch to the existing Hub interface at any time.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={() => navigate('/agents')}>Go to Advanced Hub</Button>
            </CardContent>
          </Card>
        </section>
      </div>
    </div>
  );
}
