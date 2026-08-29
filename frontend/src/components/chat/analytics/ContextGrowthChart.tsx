/**
 * ContextGrowthChart — the ONE chart on the conversation analytics pane
 * (see ConversationAnalyticsPane.tsx for why exactly one chart is allowed
 * here). Plots `series[].peak_context_tokens` against `series[].sequence`:
 * context growth over turns is a shape over an axis, which is the one
 * question the tile-based sections on this pane genuinely cannot answer.
 *
 * `peak_context_tokens` is `null` for any run whose context size could not
 * be measured (see conversationAnalytics.types.ts). A `null` is NOT zero —
 * plotting it as 0 would draw a fake cliff back to the origin. Instead each
 * null point is kept in the data (so its turn still occupies an x position)
 * but carries `value: null`, and the line is drawn with `connectNulls={false}`
 * so Recharts breaks the line across that gap instead of interpolating
 * through it or drawing it as zero.
 */
import {
  CartesianGrid,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import type { ConversationAnalyticsSeriesPoint } from '@/types/conversationAnalytics.types';

const chartConfig = {
  contextTokens: {
    label: 'Context size',
    color: 'var(--ink)',
  },
} satisfies ChartConfig;

export interface ContextGrowthChartProps {
  series: ConversationAnalyticsSeriesPoint[];
}

interface ChartDatum {
  sequence: number;
  contextTokens: number | null;
}

export function ContextGrowthChart({ series }: ContextGrowthChartProps) {
  const data: ChartDatum[] = series.map((point) => ({
    sequence: point.sequence,
    // Kept as `null`, not defaulted to 0 — see file header comment.
    contextTokens: point.peak_context_tokens,
  }));

  const hasAnyMeasurement = data.some((d) => d.contextTokens !== null);

  if (data.length === 0 || !hasAnyMeasurement) {
    return (
      <div className="flex h-[160px] items-center justify-center rounded-lg border border-line bg-panel">
        <p className="text-[12px] text-steel-soft">No measured turns to chart yet.</p>
      </div>
    );
  }

  return (
    <ChartContainer config={chartConfig} className="aspect-auto h-[180px] w-full">
      <LineChart data={data} margin={{ left: 4, right: 8, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--line)" />
        <XAxis
          dataKey="sequence"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          label={{ value: 'Turn', position: 'insideBottom', offset: -4, fontSize: 11 }}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          width={48}
          tickFormatter={(value: number) =>
            value >= 1000 ? `${(value / 1000).toFixed(0)}k` : String(value)
          }
        />
        <ChartTooltip
          content={
            <ChartTooltipContent
              labelFormatter={(label) => `Turn ${label}`}
              // No custom `formatter`: the default renderer already shows the
              // series label, and simply omits a value when it is `null` —
              // which is the correct "not measured" reading for this data,
              // never a fabricated 0.
            />
          }
        />
        <Line
          dataKey="contextTokens"
          type="monotone"
          stroke="var(--color-contextTokens)"
          strokeWidth={1.75}
          dot={{ r: 2.5 }}
          connectNulls={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ChartContainer>
  );
}

export default ContextGrowthChart;
