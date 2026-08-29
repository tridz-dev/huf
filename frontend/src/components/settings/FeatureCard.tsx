import type { ComponentType, ReactNode } from 'react';
import { ExternalLink, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';

export interface FeatureCardProps {
  /** A lucide icon component, or any custom ReactNode to use as the leading icon. */
  icon: ComponentType<{ className?: string }> | ReactNode;
  title: string;
  /** Short, benefit-focused marketing copy (2-3 sentences). */
  pitch: string;
  /** Value-prop bullets shown under the pitch. */
  bullets?: string[];
  enabled: boolean;
  onToggle: (next: boolean) => void | Promise<void>;
  /** Disables the toggle, e.g. while the async onToggle call is in flight. */
  toggleDisabled?: boolean;
  /** Shows a spinner next to the toggle instead of its normal state. */
  toggleLoading?: boolean;
  learnMoreHref?: string;
}

function isComponentIcon(
  icon: FeatureCardProps['icon']
): icon is ComponentType<{ className?: string }> {
  return typeof icon === 'function';
}

/**
 * A reusable "feature pitch" card: icon + title + marketing copy + value-prop
 * bullets + an on/off toggle. Used for optional add-on features (like DeskAI)
 * that are configured elsewhere but explained and toggled from Huf's settings.
 */
export function FeatureCard({
  icon,
  title,
  pitch,
  bullets,
  enabled,
  onToggle,
  toggleDisabled,
  toggleLoading,
  learnMoreHref,
}: FeatureCardProps) {
  const Icon = isComponentIcon(icon) ? icon : null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-[color-mix(in_srgb,var(--signal)_10%,white)]">
              {Icon ? <Icon className="h-4.5 w-4.5 text-signal" /> : (icon as ReactNode)}
            </div>
            <div>
              <h3 className="text-[14px] font-semibold text-ink">{title}</h3>
              <p className="font-body text-[13px] text-steel mt-1 max-w-prose">{pitch}</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {toggleLoading && <Loader2 className="h-4 w-4 animate-spin text-steel-soft" />}
            <Switch
              checked={enabled}
              disabled={toggleDisabled || toggleLoading}
              onCheckedChange={onToggle}
              aria-label={`${enabled ? 'Disable' : 'Enable'} ${title}`}
            />
          </div>
        </div>
      </CardHeader>
      {(bullets?.length || learnMoreHref) && (
        <CardContent className="pt-0">
          {bullets?.length ? (
            <ul className="space-y-1.5">
              {bullets.map((bullet) => (
                <li key={bullet} className="flex items-start gap-2 font-body text-[13px] text-steel">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-steel-soft" />
                  {bullet}
                </li>
              ))}
            </ul>
          ) : null}
          {learnMoreHref && (
            <a
              className="mt-3 inline-flex items-center gap-1 text-sm text-primary hover:underline"
              href={learnMoreHref}
              target="_blank"
              rel="noreferrer"
            >
              Learn more<ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </CardContent>
      )}
    </Card>
  );
}
