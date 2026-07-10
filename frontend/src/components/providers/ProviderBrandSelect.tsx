import { useMemo } from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { ProviderBrandIcon } from '@/components/providers/ProviderBrandIcon';
import { getBrandLabel, getProviderBrands, suggestBrandFromProviderName } from '@/utils/providerBrands';
import { cn } from '@/lib/utils';

interface ProviderBrandSelectProps {
  value: string;
  onChange: (value: string) => void;
  providerName?: string;
  label?: string;
  required?: boolean;
  className?: string;
}

export function ProviderBrandSelect({
  value,
  onChange,
  providerName,
  label = 'Provider Brand',
  required = false,
  className,
}: ProviderBrandSelectProps) {
  const brands = useMemo(() => getProviderBrands(), []);

  const suggestedBrand = useMemo(() => {
    if (!providerName?.trim()) {
      return undefined;
    }
    return suggestBrandFromProviderName(providerName);
  }, [providerName]);

  const displayValue = value || suggestedBrand || '';

  return (
    <div className={cn('space-y-2', className)}>
      <Label>
        {label}
        {required ? <span className="text-destructive"> *</span> : null}
      </Label>
      <Select value={displayValue} onValueChange={onChange}>
        <SelectTrigger>
          <SelectValue placeholder="Select provider brand">
            {displayValue ? (
              <span className="flex items-center gap-2">
                <ProviderBrandIcon brand={displayValue} size="xs" showFallback />
                <span>{getBrandLabel(displayValue)}</span>
              </span>
            ) : (
              'Select provider brand'
            )}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {brands.map((brand) => (
            <SelectItem key={brand.id} value={brand.id}>
              <span className="flex items-center gap-2">
                <ProviderBrandIcon brand={brand.id} size="xs" showFallback />
                <span>{brand.label}</span>
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {!value && suggestedBrand ? (
        <p className="text-xs text-muted-foreground">
          Suggested from provider name: {getBrandLabel(suggestedBrand)}
        </p>
      ) : null}
    </div>
  );
}
