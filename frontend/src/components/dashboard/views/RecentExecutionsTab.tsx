import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { getRecentAgentRuns } from '@/services/dashboardApi';
import { formatTimeAgo, calculateDuration } from '@/utils/time';
import type { AgentRunDoc } from '@/services/agentRunApi';
import { LedgerSection, LedgerRow } from '@/components/dashboard';

interface RecentExecutionsTabProps {
  runs?: AgentRunDoc[];
  loading?: boolean;
}

function getExecutionStatus(status?: string): { variant: 'run' | 'ok' | 'fail'; label: string } {
  const normalized = status?.toLowerCase();
  if (normalized === 'success') {
    return { variant: 'ok', label: 'Success' };
  }
  if (normalized === 'failed') {
    return { variant: 'fail', label: 'Failed' };
  }
  return { variant: 'run', label: status || 'Running' };
}

export function RecentExecutionsTab({ runs: providedRuns, loading: providedLoading }: RecentExecutionsTabProps) {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<AgentRunDoc[]>(providedRuns || []);
  const [loading, setLoading] = useState(providedLoading ?? true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (providedRuns !== undefined) {
      setRuns(providedRuns);
      setLoading(providedLoading ?? false);
      return;
    }

    async function fetchRecentRuns() {
      try {
        setLoading(true);
        setError(null);
        const data = await getRecentAgentRuns();
        setRuns(data);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to fetch recent executions'));
      } finally {
        setLoading(false);
      }
    }

    fetchRecentRuns();
  }, [providedRuns, providedLoading]);

  const handleExecutionClick = (run: AgentRunDoc) => {
    if (run.conversation) {
      navigate(`/chat/${run.conversation}`);
    }
  };

  return (
    <LedgerSection title="Recent executions">
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-steel-soft" />
        </div>
      ) : error ? (
        <div className="text-center py-8 text-signal-ink">
          <p className="font-body font-semibold">Failed to load executions</p>
          <p className="font-mono text-[12px] text-steel mt-1">{error.message}</p>
        </div>
      ) : runs.length === 0 ? (
        <div className="text-center py-8 text-steel font-body text-[14px]">
          No recent executions
        </div>
      ) : (
        runs.map((run) => {
          const duration = calculateDuration(run.start_time, run.end_time);
          const timeAgo = formatTimeAgo(run.start_time);
          const status = getExecutionStatus(run.status);
          const isClickable = Boolean(run.conversation);

          return (
            <LedgerRow
              key={run.name}
              name={run.agent || 'Unknown Agent'}
              sub={`run · ${run.name}`}
              meta={`${duration} · ${timeAgo}`}
              status={status}
              onClick={isClickable ? () => handleExecutionClick(run) : undefined}
            />
          );
        })
      )}
    </LedgerSection>
  );
}
