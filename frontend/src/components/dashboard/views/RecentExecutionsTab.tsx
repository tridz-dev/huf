import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { getRecentAgentRuns, type AgentRunDoc } from '@/services/dashboardApi';
import { formatTimeAgo } from '@/utils/time';

interface RecentExecutionsTabProps {
  runs?: AgentRunDoc[];
  loading?: boolean;
}

/**
 * Calculate duration between start_time and end_time
 * Returns duration in seconds or minutes, or "Not available" if invalid
 */
function calculateDuration(startTime: string | null | undefined, endTime: string | null | undefined): string {
  if (!startTime || !endTime) {
    return 'Not available';
  }

  try {
    const start = new Date(startTime);
    const end = new Date(endTime);

    // Check if dates are valid
    if (isNaN(start.getTime()) || isNaN(end.getTime())) {
      return 'Not available';
    }

    const diffInMs = end.getTime() - start.getTime();
    
    // Handle negative duration (end before start)
    if (diffInMs < 0) {
      return 'Not available';
    }

    const diffInSeconds = Math.floor(diffInMs / 1000);
    const diffInMinutes = Math.floor(diffInSeconds / 60);

    // If less than 60 seconds, show in seconds
    if (diffInSeconds < 60) {
      return `${diffInSeconds}s`;
    }

    // Otherwise show in minutes with seconds
    const remainingSeconds = diffInSeconds % 60;
    if (remainingSeconds === 0) {
      return `${diffInMinutes}m`;
    }
    return `${diffInMinutes}m ${remainingSeconds}s`;
  } catch {
    return 'Not available';
  }
}

/**
 * Get status badge variant based on status
 */
function getStatusVariant(status?: string): 'default' | 'destructive' {
  if (status === 'Success' || status === 'success') {
    return 'default';
  }
  if (status === 'Failed' || status === 'failed') {
    return 'destructive';
  }
  return 'default';
}

/**
 * Get status icon based on status
 */
function getStatusIcon(status?: string) {
  if (status === 'Success' || status === 'success') {
    return CheckCircle;
  }
  if (status === 'Failed' || status === 'failed') {
    return XCircle;
  }
  return CheckCircle;
}

export function RecentExecutionsTab({ runs: providedRuns, loading: providedLoading }: RecentExecutionsTabProps) {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<AgentRunDoc[]>(providedRuns || []);
  const [loading, setLoading] = useState(providedLoading ?? true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    // If runs are provided, use them and skip fetching
    if (providedRuns !== undefined) {
      setRuns(providedRuns);
      setLoading(providedLoading ?? false);
      return;
    }

    // Otherwise, fetch runs
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
    <Card>
      <CardHeader>
        <CardTitle>Recent Executions</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="text-center py-8 text-destructive">
            <p>Failed to load executions</p>
            <p className="text-sm text-muted-foreground mt-1">{error.message}</p>
          </div>
        ) : runs.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No recent executions
          </div>
        ) : (
          <div className="space-y-3">
            {runs.map((run) => {
              const StatusIcon = getStatusIcon(run.status);
              const duration = calculateDuration(run.start_time, run.end_time);
              const timeAgo = formatTimeAgo(run.start_time);
              const statusColor = run.status === 'Success' || run.status === 'success' 
                ? 'text-green-600' 
                : run.status === 'Failed' || run.status === 'failed'
                ? 'text-red-600'
                : 'text-muted-foreground';

              const isClickable = Boolean(run.conversation);

              return (
                <div
                  key={run.name}
                  className={`flex items-center justify-between p-3 rounded-lg border transition-colors ${
                    isClickable 
                      ? 'hover:bg-muted/50 cursor-pointer' 
                      : 'opacity-75'
                  }`}
                  onClick={() => isClickable && handleExecutionClick(run)}
                >
                  <div className="flex items-center gap-3 flex-1">
                    <StatusIcon className={`w-4 h-4 shrink-0 ${statusColor}`} />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{run.agent || 'Unknown Agent'}</div>
                      <div className="text-sm text-muted-foreground">
                        {duration} • {timeAgo}
                      </div>
                    </div>
                  </div>
                  <Badge variant={getStatusVariant(run.status)}>
                    {run.status || 'Unknown'}
                  </Badge>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

