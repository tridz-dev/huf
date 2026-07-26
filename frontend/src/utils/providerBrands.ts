import brands from '@/data/provider-brands.json';

export interface ProviderBrand {
  id: string;
  label: string;
}

const BRAND_LIST = brands as ProviderBrand[];

const BRAND_BY_ID = new Map(BRAND_LIST.map((brand) => [brand.id, brand]));

const SLUG_ALIASES: Record<string, string> = {
  bedrock: 'amazon-bedrock',
  gemini: 'google',
  grok: 'xai',
  dashscope: 'alibaba',
  huggingface: 'huggingface',
};

export function getProviderBrands(): ProviderBrand[] {
  return BRAND_LIST;
}

export function getBrandById(id: string | null | undefined): ProviderBrand | undefined {
  if (!id) return undefined;
  return BRAND_BY_ID.get(id);
}

export function getBrandLabel(id: string | null | undefined): string {
  return getBrandById(id)?.label ?? 'Other';
}

export function isKnownBrand(id: string | null | undefined): boolean {
  return Boolean(id && id !== 'other' && BRAND_BY_ID.has(id));
}

export function suggestBrandFromProviderName(providerName: string): string | undefined {
  const normalized = providerName.trim().toLowerCase().replace(/\s+/g, '-');
  const alias = SLUG_ALIASES[normalized] ?? normalized;

  if (BRAND_BY_ID.has(alias)) {
    return alias;
  }

  const match = BRAND_LIST.find(
    (brand) =>
      brand.id !== 'other' &&
      (brand.label.toLowerCase() === providerName.trim().toLowerCase() ||
        brand.id === normalized)
  );

  return match?.id;
}

/** Resolve display brand from stored brand id and/or linked provider name. */
export function resolveProviderBrand(
  brandId?: string | null,
  providerName?: string | null,
): string | undefined {
  if (isKnownBrand(brandId)) {
    return brandId!;
  }
  if (providerName) {
    return suggestBrandFromProviderName(providerName);
  }
  return undefined;
}
