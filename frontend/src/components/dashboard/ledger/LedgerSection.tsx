import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

export type StatusDotVariant = 'run' | 'idle' | 'ok' | 'fail';

export interface StatusDotProps {
  variant: StatusDotVariant;
}

export function StatusDot({ variant }: StatusDotProps) {
  return (
    <span
      className={cn(
        'w-[7px] h-[7px] rounded-full flex-none',
        variant === 'run' && 'bg-signal animate-blink motion-reduce:animate-none',
        variant === 'idle' && 'bg-steel-soft',
        variant === 'ok' && 'bg-good',
        variant === 'fail' && 'bg-signal-ink'
      )}
      aria-hidden
    />
  );
}

export interface LedgerRowProps {
  name: React.ReactNode;
  sub?: React.ReactNode;
  meta?: React.ReactNode;
  count?: React.ReactNode;
  status?: {
    variant: StatusDotVariant;
    label: string;
  };
  onClick?: () => void;
}

export function LedgerRow({
  name,
  sub,
  meta,
  count,
  status,
  onClick,
}: LedgerRowProps) {
  return (
    <div
      className={cn(
        'group grid grid-cols-[1fr_140px_28px] lg:grid-cols-[1fr_220px_90px_140px_28px] items-center gap-4 px-6 py-4 border-t border-line hover:bg-paper-deep transition-colors',
        onClick && 'cursor-pointer'
      )}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div className="min-w-0">
        <div className="font-body font-semibold text-[14.5px] truncate">{name}</div>
        {sub && (
          <div className="font-mono text-[11px] text-steel-soft mt-[3px] truncate">
            {sub}
          </div>
        )}
      </div>

      <div className="hidden lg:flex font-mono text-[12px] text-steel truncate">
        {meta}
      </div>

      <div className="hidden lg:flex font-mono text-[12px] text-steel items-center gap-1.5 truncate">
        {count}
      </div>

      {status ? (
        <div className="flex items-center gap-2">
          <StatusDot variant={status.variant} />
          <span className="font-body text-[13px] font-medium text-steel hidden lg:inline">
            {status.label}
          </span>
        </div>
      ) : (
        <div />
      )}

      <ChevronRight
        className="w-4 h-4 text-steel-soft group-hover:text-ink transition-colors justify-self-end"
        strokeWidth={1.8}
      />
    </div>
  );
}

export interface LedgerSectionProps {
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

export function LedgerSection({ title, children, footer }: LedgerSectionProps) {
  return (
    <div className="border border-line border-t-0 bg-panel">
      <div className="font-display font-bold text-[18px] tracking-[.02em] px-6 pt-[18px] pb-2.5">
        {title}
      </div>
      <div>{children}</div>
      {footer && <div className="border-t border-line px-6 py-3">{footer}</div>}
    </div>
  );
}
