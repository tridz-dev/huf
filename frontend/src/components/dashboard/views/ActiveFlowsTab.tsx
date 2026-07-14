import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Zap, Loader2 } from 'lucide-react';
import { getDashboardActiveFlows, type DashboardFlowItem } from '@/services/dashboardApi';
import { formatTimeAgo } from '@/utils/time';
import type { FlowStatus } from '@/types/flow.types';
import { LedgerSection, LedgerRow } from '@/components/dashboard';

interface ActiveFlowsTabProps {
  flows?: DashboardFlowItem[];
  loading?: boolean;
}

function getFlowStatusVariant(status: FlowStatus): { variant: 'run' | 'idle' | 'ok' | 'fail'; label: string } {
  switch (status) {
    case 'active':
      return { variant: 'ok', label: 'Active' };
    case 'paused':
      return { variant: 'idle', label: 'Paused' };
    case 'error':
      return { variant: 'fail', label: 'Error' };
    default:
      return { variant: 'idle', label: 'Draft' };
  }
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
    <LedgerSection title="Active flows">
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-steel-soft" />
        </div>
      ) : error ? (
        <div className="text-center py-8 text-signal-ink">
          <p className="font-body font-semibold">Failed to load flows</p>
          <p className="font-mono text-[12px] text-steel mt-1">{error.message}</p>
        </div>
      ) : flows.length === 0 ? (
        <div className="text-center py-8 text-steel font-body text-[14px]">
          No active flows
        </div>
      ) : (
        flows.map((flow) => {
          const status = getFlowStatusVariant(flow.status);
          return (
            <LedgerRow
              key={flow.id}
              name={flow.name}
              sub={flow.lastRunAt ? `Last run ${formatTimeAgo(flow.lastRunAt)}` : undefined}
              meta={status.label}
              count={
                <>
                  <Zap className="w-[13px] h-[13px] text-steel-soft" />
                  {flow.runCount}
                </>
              }
              status={status}
              onClick={() => handleFlowClick(flow.id)}
            />
          );
        })
      )}
    </LedgerSection>
  );
}
