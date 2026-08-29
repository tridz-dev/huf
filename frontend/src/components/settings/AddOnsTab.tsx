import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Bot, PackageX } from 'lucide-react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { FeatureCard } from '@/components/settings/FeatureCard';
import { getDeskAiSettings, updateDeskAiSettings } from '@/services/deskAiSettingsApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';

export { AddOnsTab };
export default AddOnsTab;

const DESKAI_BULLETS = [
  'Works on any Desk page — forms, lists, reports',
  'Understands what you’re pointing at — fields, sections, tabs, buttons',
  'Backed by the same knowledge and tools as your Huf agents',
  'No context switching — assistance where the work happens',
];

const DESKAI_PITCH =
  'DeskAI puts an AI assistant directly inside Frappe Desk — navigate, fill forms, answer questions ' +
  'about ERPNext data, and act on documents without leaving the page you’re on. It brings the same ' +
  'intelligence powering your Huf agents right into the tools your team already uses every day.';

type LoadState = 'loading' | 'ready' | 'not-installed';

function AddOnsTab() {
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [enabled, setEnabled] = useState(false);
  const [toggling, setToggling] = useState(false);

  useEffect(() => {
    let cancelled = false;

    getDeskAiSettings()
      .then((settings) => {
        if (cancelled) return;
        setEnabled(settings.enabled === 1);
        setLoadState('ready');
      })
      .catch((error) => {
        if (cancelled) return;
        // The `deskai` app is optional. If its `DeskAI Settings` doctype
        // doesn't exist on this site, the read 404s — treat that as
        // "not installed" rather than a failure to surface.
        console.warn('DeskAI Settings unavailable (deskai app likely not installed):', error);
        setLoadState('not-installed');
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleToggle = async (next: boolean) => {
    const previous = enabled;
    setEnabled(next);
    setToggling(true);
    try {
      await updateDeskAiSettings({ enabled: next ? 1 : 0 });
      toast.success(`DeskAI ${next ? 'enabled' : 'disabled'}`);
    } catch (error) {
      setEnabled(previous);
      toast.error('Failed to update DeskAI settings', {
        description: getFrappeErrorMessage(error),
        duration: 8000,
      });
    } finally {
      setToggling(false);
    }
  };

  if (loadState === 'loading') {
    return null;
  }

  if (loadState === 'not-installed') {
    return (
      <Card className="border-dashed">
        <CardHeader>
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted">
              <PackageX className="h-4.5 w-4.5 text-steel-soft" />
            </div>
            <div>
              <h3 className="text-[14px] font-semibold text-ink">DeskAI</h3>
              <p className="font-body text-[13px] text-steel mt-1 max-w-prose">
                DeskAI brings an AI assistant into Frappe Desk. Install the DeskAI app on this site to
                enable it here.
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0" />
      </Card>
    );
  }

  return (
    <FeatureCard
      icon={Bot}
      title="DeskAI"
      pitch={DESKAI_PITCH}
      bullets={DESKAI_BULLETS}
      enabled={enabled}
      onToggle={handleToggle}
      toggleLoading={toggling}
    />
  );
}
