import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { getAgentsForSource } from "@/services/knowledge/usageApi";

/** "Used by N agents" link; opens a small list of those agents. */
export function AgentUsageLink({
  knowledgeSource,
  onConnect,
  refreshKey = 0,
}: {
  knowledgeSource: string;
  onConnect?: () => void;
  refreshKey?: number;
}) {
  const [agents, setAgents] = useState<string[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAgentsForSource(knowledgeSource)
      .then((a) => !cancelled && setAgents(a))
      .catch(() => !cancelled && setAgents([]));
    return () => {
      cancelled = true;
    };
  }, [knowledgeSource, refreshKey]);

  if (agents === null) return null;
  if (agents.length === 0) {
    return (
      <button
        type="button"
        onClick={onConnect}
        className="text-sm text-signal-ink underline-offset-4 hover:underline"
        data-testid="agent-usage"
      >
        Connect to an agent →
      </button>
    );
  }
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="text-sm text-signal-ink underline-offset-4 hover:underline"
          data-testid="agent-usage"
        >
          Used by {agents.length} {agents.length === 1 ? "agent" : "agents"}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-2">
        <ul className="space-y-0.5">
          {agents.map((a) => (
            <li key={a}>
              <Link
                to={`/agents/${encodeURIComponent(a)}`}
                className="block truncate rounded px-2 py-1.5 text-sm hover:bg-muted"
              >
                {a}
              </Link>
            </li>
          ))}
        </ul>
        {onConnect && (
          <button type="button" onClick={onConnect} className="mt-1 w-full rounded px-2 py-1.5 text-left text-sm text-signal-ink hover:bg-muted">
            Connect another agent →
          </button>
        )}
      </PopoverContent>
    </Popover>
  );
}
