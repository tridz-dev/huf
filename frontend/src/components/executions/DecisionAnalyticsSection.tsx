import { useEffect, useState } from 'react';
import { EmptyStat, GaugeRow, MetricGauge } from '@/components/dashboard';
import {
  getDecisionSpendSummary,
  type DecisionSpendSummary,
} from '@/services/decisionApi';
import { Loader2 } from 'lucide-react';

const number = new Intl.NumberFormat();

// Empty metric cell (when no data available)
function EmptyMetric({ label, caption }: { label: string; caption: string }) {
  return (
    <div className="px-[18px] py-4 min-w-0">
      <EmptyStat label={label} caption={caption} />
    </div>
  );
}

export interface DecisionAnalyticsSectionProps {
  /** ISO start of the analytics window. Omit for the API's own default (last 7 days). */
  fromDate?: string;
  /** ISO end of the analytics window. */
  toDate?: string;
}

/**
 * Decision Analytics Section — metric strip and spend breakdowns.
 *
 * Shows: total calls, total spend, success rate, and spend breakdown by policy/agent/surface/deployment.
 */
export function DecisionAnalyticsSection({ fromDate, toDate }: DecisionAnalyticsSectionProps) {
  const [summary, setSummary] = useState<DecisionSpendSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    getDecisionSpendSummary({
      from_date: fromDate,
      to_date: toDate,
      group_by: 'policy',
    })
      .then((summaryData) => {
        if (cancelled) return;
        setSummary(summaryData);
        setLoading(false);
      })
      .catch((error) => {
        console.error('Error loading decision analytics:', error);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [fromDate, toDate]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-4 px-[18px]">
        <Loader2 className="h-4 w-4 animate-spin text-steel-soft mr-2" />
        <span className="font-body text-[13px] text-steel">Loading decision analytics…</span>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="px-[18px] py-4 font-body text-[13px] text-steel-soft">
        No decision data available in this period.
      </div>
    );
  }

  const totalCalls = summary.summary.call_count;
  const totalCost = summary.summary.cost;
  const totalTokens = summary.summary.total_tokens;

  return (
    <div>
      {/* Metric Strip */}
      <GaugeRow className="rounded-none border-0">
        <MetricGauge
          label="Decision Calls"
          value={number.format(totalCalls)}
          info={`${summary.summary.input_tokens.toLocaleString()} input tokens`}
        />
        <MetricGauge
          label="Total Spend"
          value={`$${totalCost.toFixed(4)}`}
          info={`${number.format(totalTokens)} total tokens`}
        />
        {totalCalls > 0 ? (
          <MetricGauge
            label="Avg Cost"
            value={`$${(totalCost / totalCalls).toFixed(6)}`}
            info="Per decision call"
          />
        ) : (
          <EmptyMetric label="Avg Cost" caption="No calls in this period." />
        )}
        <MetricGauge
          label="Deployment"
          value={summary.breakdowns.length > 0 ? summary.breakdowns[0].dimension_value : 'N/A'}
          info="Top deployment by cost"
        />
      </GaugeRow>

      {/* Spend Breakdown by Policy */}
      <div className="border-t border-line px-[18px] py-4">
        <h3 className="font-medium text-sm text-steel mb-3">Spend by Policy</h3>
        {summary.breakdowns.length > 0 ? (
          <div className="space-y-2">
            {summary.breakdowns.slice(0, 5).map((breakdown, idx) => (
              <div key={idx} className="flex items-center justify-between text-sm">
                <span className="text-steel-soft">{breakdown.dimension_value || 'Unknown'}</span>
                <div className="flex items-center gap-4">
                  <span className="text-steel tabular-nums">{number.format(breakdown.call_count)} calls</span>
                  <span className="text-steel tabular-nums font-medium">${breakdown.cost.toFixed(4)}</span>
                </div>
              </div>
            ))}
            {summary.breakdowns.length > 5 && (
              <p className="text-xs text-steel-soft pt-2">+{summary.breakdowns.length - 5} more policies</p>
            )}
          </div>
        ) : (
          <p className="text-xs text-steel-soft">No policy data available.</p>
        )}
      </div>

      <p className="border-t border-line px-[18px] py-2.5 font-body text-[12px] text-steel-soft">
        Decision spend metrics are read from aggregated call data over the selected period.
      </p>
    </div>
  );
}
