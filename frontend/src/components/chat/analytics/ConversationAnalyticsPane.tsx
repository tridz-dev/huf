/**
 * ConversationAnalyticsPane — right-docked pane showing token/cost/context
 * analytics for the open conversation, fetched from
 * `getConversationAnalytics` (see conversationAnalyticsApi.ts).
 *
 * Chrome (border-l, fixed px width, header row, drag-to-resize handle on the
 * left edge, scrollable body) intentionally mirrors ArtifactPreviewPane.tsx
 * rather than sharing code with it: ArtifactPreviewPane is owned by another
 * concurrent work stream and is off-limits to edit here, so duplicating its
 * ~15 lines of resize-drag plumbing is the least invasive way to get a
 * visually consistent second pane. Both panes read and write the same
 * `width`/`onWidthChange` pair (owned by `useArtifactPane` in ChatPageV2.tsx)
 * so the slot keeps one remembered size regardless of which tab is showing.
 *
 * THE CENTRAL INVARIANT: `totals` (cumulative, summed across every run) and
 * `current` (a snapshot of only the latest run) describe different kinds of
 * quantities — a running sum vs. one point in time. This component renders
 * them as two visually and textually separate sections and never divides
 * one by the other or otherwise combines them into a single "share"/percent
 * figure. Do not "simplify" them together — that is the exact misleading
 * aggregation this pane exists to prevent. See conversationAnalytics.types.ts.
 */
import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { getConversationAnalytics } from '@/services/conversationAnalyticsApi';
import type {
  ConversationAnalyticsResponse,
  ConversationRunKind,
} from '@/types/conversationAnalytics.types';
import { GaugeRow, MetricGauge } from '@/components/dashboard/cards/MetricGauge';
import { EmptyStat } from '@/components/dashboard/views/EmptyState';
import { ContextGrowthChart } from './ContextGrowthChart';

export interface ConversationAnalyticsPaneProps {
  /** Conversation to show analytics for, or null when the pane should render nothing. */
  conversationId: string | null;
  onClose: () => void;
  /** Current pane width in px, shared with the artifact pane (see file header). */
  width: number;
  onWidthChange: (px: number) => void;
}

const RUN_KIND_LABEL: Record<ConversationRunKind, string> = {
  agent: 'agent',
  tool: 'tool',
  orchestrator: 'orchestrator',
};

function formatCount(n: number): string {
  return n.toLocaleString();
}

function formatTokens(n: number): string {
  return n.toLocaleString();
}

function formatCost(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(n);
}

function formatPercent(ratio: number): string {
  return `${(ratio * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function formatDurationMs(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

function runKindBreakdown(byKind: Record<ConversationRunKind, number>): string {
  return (Object.keys(RUN_KIND_LABEL) as ConversationRunKind[])
    .map((kind) => [kind, byKind[kind] ?? 0] as const)
    .filter(([, count]) => count > 0)
    .map(([kind, count]) => `${count} ${RUN_KIND_LABEL[kind]}`)
    .join(' · ');
}

export function ConversationAnalyticsPane({
  conversationId,
  onClose,
  width,
  onWidthChange,
}: ConversationAnalyticsPaneProps) {
  const [isResizing, setIsResizing] = useState(false);
  const [data, setData] = useState<ConversationAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!conversationId) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getConversationAnalytics(conversationId).then((result) => {
      if (cancelled) return;
      setData(result);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  useEffect(() => {
    if (!isResizing) return;
    const handleMouseMove = (e: MouseEvent) => {
      onWidthChange(window.innerWidth - e.clientX);
    };
    const handleMouseUp = () => setIsResizing(false);
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.body.style.userSelect = previousUserSelect;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing, onWidthChange]);

  if (!conversationId) {
    return null;
  }

  return (
    <div
      className="relative flex h-full shrink-0 flex-col border-l border-line bg-paper"
      style={{ width }}
    >
      <div
        className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-primary/50 transition-colors"
        onMouseDown={handleMouseDown}
      />

      <div className="flex h-chat-header flex-none items-center gap-2.5 border-b border-line px-3.5">
        <h2 className="min-w-0 flex-1 truncate text-[13px] font-medium">Analytics</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close analytics"
          className="text-steel hover:text-ink"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3.5 py-4">
        {loading && !data && (
          <p className="text-[12px] text-steel-soft">Loading analytics...</p>
        )}
        {!loading && !data && (
          <p className="text-[12px] text-steel-soft">
            Analytics are not available for this conversation.
          </p>
        )}
        {data && <AnalyticsSections data={data} />}
      </div>
    </div>
  );
}

function AnalyticsSections({ data }: { data: ConversationAnalyticsResponse }) {
  const { totals, current, series, cache, measurement } = data;
  const breakdown = runKindBreakdown(totals.run_count_by_kind);

  return (
    <div className="flex flex-col gap-6">
      {/* --- Cumulative: a running sum over every run so far. --- */}
      <section>
        <SectionHeading title="Totals" caption="Summed across every run in this conversation" />
        <GaugeRow className="mt-2">
          <MetricGauge
            label="Runs"
            value={formatCount(totals.run_count)}
            unit={breakdown || undefined}
          />
          <MetricGauge label="Billed input" value={formatTokens(totals.billed_input_tokens)} unit="tokens" />
          <MetricGauge label="Output" value={formatTokens(totals.output_tokens)} unit="tokens" />
          <MetricGauge label="Cost" value={formatCost(totals.cost)} />
        </GaugeRow>
        <GaugeRow className="mt-2">
          <MetricGauge label="Cache read" value={formatTokens(totals.cache_read_tokens)} unit="tokens" />
          <MetricGauge label="Cache write" value={formatTokens(totals.cache_write_tokens)} unit="tokens" />
          {totals.average_duration_ms !== null ? (
            <MetricGauge
              label="Avg duration"
              value={formatDurationMs(totals.average_duration_ms)}
              info={`Averaged over ${formatCount(totals.duration_count)} of ${formatCount(totals.run_count)} run(s) with a recorded end time`}
            />
          ) : (
            <div className="px-[18px] py-4 min-w-0">
              <EmptyStat label="Avg duration" caption="No completed runs yet" />
            </div>
          )}
        </GaugeRow>
      </section>

      {/* --- Current: a snapshot of the latest run only, never summed. --- */}
      <section>
        <SectionHeading title="Current context" caption="Snapshot of the latest turn — not a total" />
        {current ? (
          <div className="mt-2 flex flex-col gap-2">
            <GaugeRow>
              <MetricGauge
                label="Largest turn"
                value={current.peak_context_tokens !== null ? formatTokens(current.peak_context_tokens) : '—'}
                unit={current.peak_context_tokens !== null ? 'tokens' : undefined}
                info="Peak context size measured on the most recent run."
              />
              <MetricGauge
                label="Context window"
                value={current.model_context_window !== null ? formatTokens(current.model_context_window) : '—'}
                unit={current.model_context_window !== null ? 'tokens' : undefined}
              />
              {current.context_fullness !== null ? (
                <MetricGauge label="Context fullness" value={formatPercent(current.context_fullness)} />
              ) : (
                <div className="px-[18px] py-4 min-w-0">
                  <EmptyStat
                    label="Context fullness"
                    caption="Not measured"
                  />
                </div>
              )}
              {current.duration_ms !== null ? (
                <MetricGauge label="This turn" value={formatDurationMs(current.duration_ms)} />
              ) : (
                <div className="px-[18px] py-4 min-w-0">
                  <EmptyStat label="This turn" caption="Not measured" />
                </div>
              )}
            </GaugeRow>
            <CompositionList
              segmentTokens={current.segment_tokens}
              toolExchangeTokens={current.tool_exchange_tokens}
            />
          </div>
        ) : (
          <p className="mt-2 text-[12px] text-steel-soft">No runs recorded yet for this conversation.</p>
        )}
      </section>

      {/* --- Cache effectiveness --- */}
      <section>
        <SectionHeading title="Cache effectiveness" />
        <GaugeRow className="mt-2">
          {cache.effectiveness !== null ? (
            <MetricGauge
              label="Effectiveness"
              value={formatPercent(cache.effectiveness)}
              info="An indicator of prompt-prefix stability across runs, not a measurement confirmed by the provider."
            />
          ) : (
            <div className="px-[18px] py-4 min-w-0">
              <EmptyStat label="Effectiveness" caption="No billed input to measure against" />
            </div>
          )}
          <MetricGauge label="Uncached input" value={formatTokens(cache.uncached_input_tokens)} unit="tokens" />
        </GaugeRow>
        <p className="mt-2 text-[11px] leading-relaxed text-steel-soft">
          Cache effectiveness is an indicator of prompt-prefix stability, not a value the provider
          confirms directly.
        </p>
      </section>

      {/* --- Measurement disclosure --- */}
      <MeasurementDisclosure measurement={measurement} />

      {/* --- The one chart on this pane: context growth over turns. --- */}
      <section>
        <SectionHeading title="Context growth" caption="Largest context size measured per turn" />
        <div className="mt-2">
          <ContextGrowthChart series={series} />
        </div>
      </section>
    </div>
  );
}

function SectionHeading({ title, caption }: { title: string; caption?: string }) {
  return (
    <div>
      <h3 className="text-[12px] font-semibold uppercase tracking-wide text-ink">{title}</h3>
      {caption && <p className="text-[11px] text-steel-soft">{caption}</p>}
    </div>
  );
}

function CompositionList({
  segmentTokens,
  toolExchangeTokens,
}: {
  segmentTokens: Record<string, number | null> | null;
  toolExchangeTokens: number | null;
}) {
  const hasSegments = segmentTokens !== null && Object.keys(segmentTokens).length > 0;

  if (!hasSegments && toolExchangeTokens === null) {
    return <p className="text-[11px] text-steel-soft">Composition not measured for the latest turn.</p>;
  }

  return (
    <div className="rounded-lg border border-line bg-panel px-3.5 py-3">
      <div className="text-[11px] font-medium text-steel-soft">Composition</div>
      <dl className="mt-1.5 flex flex-col gap-1">
        {hasSegments &&
          Object.entries(segmentTokens).map(([segment, value]) => (
            <div key={segment} className="flex items-center justify-between text-[12px]">
              <dt className="capitalize text-steel">{segment.replace(/_/g, ' ')}</dt>
              <dd className="font-mono tabular-nums text-ink">
                {value !== null ? `${formatTokens(value)} tokens` : 'not measured'}
              </dd>
            </div>
          ))}
        <div className="flex items-center justify-between text-[12px]">
          <dt className="text-steel">Tool exchange</dt>
          <dd className="font-mono tabular-nums text-ink">
            {toolExchangeTokens !== null ? `${formatTokens(toolExchangeTokens)} tokens` : 'not measured'}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function MeasurementDisclosure({
  measurement,
}: {
  measurement: ConversationAnalyticsResponse['measurement'];
}) {
  const { runs_missing_billed_input, runs_missing_peak_context, tool_runs_without_conversation_note } =
    measurement;
  const hasAnyGap =
    runs_missing_billed_input > 0 || runs_missing_peak_context > 0 || tool_runs_without_conversation_note > 0;

  return (
    <section>
      <SectionHeading title="Measurement notes" />
      {!hasAnyGap ? (
        <p className="mt-2 text-[11px] text-steel-soft">
          Every run in this conversation was fully measured.
        </p>
      ) : (
        <div className="mt-2 flex flex-col gap-2">
          {runs_missing_billed_input > 0 && (
            <p className="text-[11px] leading-relaxed text-steel">
              {formatCount(runs_missing_billed_input)} run(s) fall back to legacy token counts — billed
              input was not separately measured for them.
            </p>
          )}
          {runs_missing_peak_context > 0 && (
            <p className="text-[11px] leading-relaxed text-steel">
              {formatCount(runs_missing_peak_context)} run(s) have no recorded peak context size.
            </p>
          )}
          {tool_runs_without_conversation_note > 0 && (
            <div className="flex gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2.5">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />
              <p className="text-[11px] leading-relaxed text-ink">
                {formatCount(tool_runs_without_conversation_note)} older tool run(s) were created before
                conversation linking existed and cannot be retro-linked. The totals above under-report
                this conversation's real usage by that amount.
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default ConversationAnalyticsPane;
