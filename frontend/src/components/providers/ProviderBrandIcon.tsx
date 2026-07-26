import { Plug } from 'lucide-react';
import { ModelSelectorLogo } from '@/components/ai-elements/model-selector';
import { cn } from '@/lib/utils';
import { isKnownBrand } from '@/utils/providerBrands';

interface ProviderBrandIconProps {
  brand?: string | null;
  className?: string;
  size?: 'xs' | 'sm' | 'md';
  showFallback?: boolean;
}

const CONTAINER_SIZE = {
  xs: 'size-5',
  sm: 'size-5',
  md: 'size-6',
} as const;

const LOGO_SIZE = {
  xs: 'size-3.5',
  sm: 'size-4',
  md: 'size-[18px]',
} as const;

const FALLBACK_ICON_SIZE = {
  xs: 'size-3',
  sm: 'size-3',
  md: 'size-3.5',
} as const;

const PILL_CLASS =
  'inline-flex shrink-0 items-center justify-center rounded-md bg-line-dark ring-1 ring-border';

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
        className={cn(PILL_CLASS, 'text-paper', CONTAINER_SIZE[size], className)}
        aria-hidden
      >
        <Plug className={FALLBACK_ICON_SIZE[size]} />
      </span>
    );
  }

  return (
    <span className={cn(PILL_CLASS, CONTAINER_SIZE[size], className)} aria-hidden>
      <ModelSelectorLogo
        provider={brand!}
        className={cn(LOGO_SIZE[size], 'object-contain brightness-0 invert')}
      />
    </span>
  );
}
