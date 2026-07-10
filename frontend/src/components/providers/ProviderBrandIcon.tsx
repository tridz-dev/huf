import { Plug } from 'lucide-react';
import { ModelSelectorLogo } from '@/components/ai-elements/model-selector';
import { cn } from '@/lib/utils';
import { isKnownBrand } from '@/utils/providerBrands';

interface ProviderBrandIconProps {
  brand?: string | null;
  className?: string;
  size?: 'sm' | 'md';
  showFallback?: boolean;
}

const SIZE_CLASSES = {
  sm: 'size-4',
  md: 'size-5',
} as const;

export function ProviderBrandIcon({
  brand,
  className,
  size = 'sm',
  showFallback = false,
}: ProviderBrandIconProps) {
  if (!isKnownBrand(brand)) {
    if (!showFallback) {
      return null;
    }

    return (
      <span
        className={cn(
          'inline-flex shrink-0 items-center justify-center rounded-md border border-border bg-muted text-muted-foreground',
          SIZE_CLASSES[size],
          className
        )}
        aria-hidden
      >
        <Plug className="size-2.5" />
      </span>
    );
  }

  return (
    <ModelSelectorLogo
      provider={brand!}
      className={cn('shrink-0', SIZE_CLASSES[size], className)}
    />
  );
}
