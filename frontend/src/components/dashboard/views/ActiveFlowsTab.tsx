import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2 } from 'lucide-react';
import { getDashboardActiveFlows, type DashboardFlowItem } from '@/services/dashboardApi';
import { formatTimeAgo } from '@/utils/time';
import type { FlowStatus } from '@/types/flow.types';

interface ActiveFlowsTabProps {
  flows?: DashboardFlowItem[];
  loading?: boolean;
}

function getStatusVariant(status: FlowStatus): 'default' | 'secondary' | 'outline' {
  switch (status) {
    case 'active':
      return 'default';
    case 'paused':
      return 'secondary';
    default:
      return 'outline';
  }
}

function getStatusLabel(status: FlowStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function ActiveFlowsTab({ flows: providedFlows, loading: providedLoading }: ActiveFlowsTabProps) {
  const navigate = useNavigate();
  const [flows, setFlows] = useState<DashboardFlowItem[]>(providedFlows || []);
  const [loading, setLoading] = useState(providedLoading ?? true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (providedFlows !== undefined) {
      setFlows(providedFlows);
      setLoading(providedLoading ?? false);
      return;
    }

    async function fetchActiveFlows() {
      try {
        setLoading(true);
        setError(null);
        const data = await getDashboardActiveFlows(10);
        setFlows(data);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to fetch flows'));
      } finally {
        setLoading(false);
      }
    }

    fetchActiveFlows();
  }, [providedFlows, providedLoading]);

  const handleFlowClick = (flowId: string) => {
    navigate(`/flows/${flowId}`);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Active Flows</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="text-center py-8 text-destructive">
            <p>Failed to load flows</p>
            <p className="text-sm text-muted-foreground mt-1">{error.message}</p>
          </div>
        ) : flows.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No active flows
          </div>
        ) : (
          <div className="space-y-3">
            {flows.map((flow) => (
              <div
                key={flow.id}
                className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 transition-colors cursor-pointer"
                onClick={() => handleFlowClick(flow.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{flow.name}</div>
                  <div className="text-sm text-muted-foreground">
                    {flow.runCount} runs • Last run {formatTimeAgo(flow.lastRunAt)}
                  </div>
                </div>
                <Badge variant={getStatusVariant(flow.status)}>
                  {getStatusLabel(flow.status)}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
