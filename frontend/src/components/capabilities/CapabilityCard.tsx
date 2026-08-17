import { cn } from '@/lib/utils';
import { CapabilityBadges } from './CapabilityBadges';
import type { CapabilityDescriptor } from '@/types/capability.types';

interface CapabilityCardProps {
  capability: CapabilityDescriptor;
  onSelect: (capability: CapabilityDescriptor) => void;
  className?: string;
}

export function CapabilityCard({ capability, onSelect, className }: CapabilityCardProps) {
  const handleClick = () => {
    onSelect(capability);
  };

  const technicalRef = capability.function_path || capability.resource_doctype;

  return (
    <div
      onClick={handleClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleClick();
        }
      }}
      role="button"
      tabIndex={0}
      className={cn(
        'flex flex-col gap-1.5 rounded-lg border p-3 transition-colors',
        'hover:bg-paper-deep cursor-pointer',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-medium">{capability.title}</h4>
      </div>
      {capability.short_description && (
        <p className="text-xs text-muted-foreground line-clamp-2">
          {capability.short_description}
        </p>
      )}
      <CapabilityBadges capability={capability} />
      {technicalRef && (
        <p className="mt-0.5 font-mono text-[10px] text-steel-soft truncate">{technicalRef}</p>
      )}
    </div>
  );
}
