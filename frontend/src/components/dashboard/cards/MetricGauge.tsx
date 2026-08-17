import { Info } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

export interface MetricGaugeProps {
  label: string;
  period?: string;
  value: string | number;
  unit?: string;
  info?: string;
}

export function MetricGauge({
  label,
  period,
  value,
  unit,
  info,
}: MetricGaugeProps) {
  return (
    <div className="px-[18px] py-4 min-w-0">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-body text-[11px] font-medium text-steel-soft">
            {label}
          </div>
          {period && (
            <div className="font-mono text-eyebrow uppercase text-steel-soft mt-1">
              {period}
            </div>
          )}
        </div>
        {info && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Info
                className="h-[15px] w-[15px] text-steel-soft cursor-help shrink-0 mt-0.5"
                strokeWidth={1.6}
              />
            </TooltipTrigger>
            <TooltipContent>
              <p className="max-w-xs font-mono text-[11px]">{info}</p>
            </TooltipContent>
          </Tooltip>
        )}
      </div>
      <div className="mt-4 flex items-baseline">
        {/* Figures stay ink black — the design system reserves violet for state
            and selection, and calls out "one dashboard figure is violet for no
            stated reason" as a defect. A delta may carry semantic colour; the
            figure itself never does. */}
        <span
          className={cn(
            'font-display font-semibold text-[22px] tracking-[-.02em] leading-none tabular-nums',
            'text-ink',
          )}
        >
          {value}
        </span>
        {unit && (
          <span className="font-mono text-base text-steel ml-1">{unit}</span>
        )}
      </div>
    </div>
  );
}

export interface GaugeRowProps {
  children: React.ReactNode;
  className?: string;
}

export function GaugeRow({ children, className }: GaugeRowProps) {
  return (
    <TooltipProvider>
      <div
        className={cn(
          'border border-line rounded-lg bg-panel grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 divide-x divide-y divide-line overflow-hidden',
          className
        )}
      >
        {children}
      </div>
    </TooltipProvider>
  );
}
