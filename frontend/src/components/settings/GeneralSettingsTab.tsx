import { useEffect, useState } from 'react';
import { Image, RotateCcw, Wrench } from 'lucide-react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { usePermissions } from '@/contexts/PermissionsContext';
import { runErpnextDemoSetup } from '@/services/erpnextDemoSetupApi';
import {
  type HufTheme,
  getTheme,
  setTheme,
  isSceneryEnabled,
  setSceneryEnabled,
  getSceneryOpacity,
  setSceneryOpacity,
} from '@/lib/personalization';

export { GeneralSettingsTab };
export { isSceneryEnabled, setSceneryEnabled };
export default GeneralSettingsTab;

const DEFAULT_THEME: HufTheme = 'winter';
const DEFAULT_OPACITY = 55;

// Theme switching is disabled — the app ships a single apple-quiet UI direction now
// (see src/index.css :root); re-enable if runtime theme switching returns.
const THEME_PICKER_ENABLED = false;

const THEMES: { id: HufTheme; label: string; preview: string[] }[] = [
  {
    id: 'winter',
    label: 'Winter',
    preview: ['#EEF0EC', '#FBFCFA', '#15181C', '#C6511F'],
  },
  {
    id: 'midnight',
    label: 'Midnight',
    preview: ['#14161A', '#1E2126', '#EDEFEA', '#FF7A3D'],
  },
  {
    id: 'summer',
    label: 'Summer',
    preview: ['#FFF3D6', '#FFFCF3', '#1C1608', '#FF5A1F'],
  },
  {
    id: 'morning',
    label: 'Morning',
    preview: ['#FBE4D6', '#FFF8F4', '#241511', '#E8531F'],
  },
];

interface GeneralSettingsTabProps {
  scenery?: boolean;
  onSceneryChange?: (enabled: boolean) => void;
  opacity?: number;
  onOpacityChange?: (opacity: number) => void;
}

function GeneralSettingsTab({
  scenery: sceneryProp,
  onSceneryChange,
  opacity: opacityProp,
  onOpacityChange,
}: GeneralSettingsTabProps = {}) {
  const [theme, setThemeState] = useState<HufTheme>(DEFAULT_THEME);
  const [internalScenery, setInternalScenery] = useState<boolean>(false);
  const [internalOpacity, setInternalOpacity] = useState<number>(DEFAULT_OPACITY);
  const { hufRole } = usePermissions();
  // Backend maps Administrator / System Manager to the "Huf Admin" Huf role.
  const isAdmin = hufRole === 'Huf Admin';
  const [demoSetupRunning, setDemoSetupRunning] = useState(false);

  const scenery = sceneryProp ?? internalScenery;
  const opacity = opacityProp ?? internalOpacity;

  useEffect(() => {
    setThemeState(getTheme());
    if (sceneryProp === undefined) {
      setInternalScenery(isSceneryEnabled());
    }
    if (opacityProp === undefined) {
      setInternalOpacity(getSceneryOpacity());
    }
  }, [sceneryProp, opacityProp]);

  const handleThemeChange = (id: HufTheme) => {
    setThemeState(id);
    setTheme(id);
  };

  const handleResetTheme = () => {
    handleThemeChange(DEFAULT_THEME);
  };

  const handleToggleScenery = () => {
    const next = !scenery;
    if (onSceneryChange) {
      onSceneryChange(next);
    }
    setInternalScenery(next);
    setSceneryEnabled(next);
  };

  const handleOpacityChange = (value: number) => {
    const clamped = Math.max(0, Math.min(100, value));
    if (onOpacityChange) {
      onOpacityChange(clamped);
    }
    setInternalOpacity(clamped);
    setSceneryOpacity(clamped);
  };

  const handleErpnextDemoSetup = async () => {
    setDemoSetupRunning(true);
    try {
      const result = await runErpnextDemoSetup();
      if (!result) {
        return;
      }
      if (result.skipped_reason) {
        toast.info(`Skipped: ${result.skipped_reason}`);
        return;
      }
      if (result.created.length === 0) {
        toast.success('ERPNext demo data already set up — nothing new to create');
      } else {
        toast.success(`Created ${result.created.length} ERPNext demo record(s)`, {
          description: result.created.join(', '),
        });
      }
    } finally {
      setDemoSetupRunning(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-6">
      <p className="text-sm text-muted-foreground">
        Personalize the HUF interface. These preferences are stored locally in your browser.
      </p>

      {THEME_PICKER_ENABLED && (
        <Card>
          <CardHeader>
            <CardTitle>Theme</CardTitle>
            <CardDescription>
              Choose a color theme. The whole interface updates instantly because every surface,
              border, and accent reads from the same set of CSS custom properties.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {THEMES.map(({ id, label, preview }) => (
                <Button
                  key={id}
                  type="button"
                  variant="outline"
                  onClick={() => handleThemeChange(id)}
                  className={cn(
                    'h-auto flex-col items-start gap-2 rounded-lg border-2 p-3 text-left',
                    theme === id
                      ? 'border-ink'
                      : 'border-line hover:border-steel-soft',
                  )}
                >
                  <div className="flex gap-1">
                    {preview.map((color) => (
                      <span
                        key={color}
                        className="w-4 h-4 rounded-sm"
                        style={{ backgroundColor: color }}
                      />
                    ))}
                  </div>
                  <span className="text-xs font-medium text-ink">{label}</span>
                </Button>
              ))}
            </div>

            <Button variant="ghost" size="sm" onClick={handleResetTheme} className="-ml-2">
              <RotateCcw className="w-4 h-4 mr-1.5" />
              Reset to Winter
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Hub scenery</CardTitle>
          <CardDescription>
            Toggle a full-page background image on the Hub. The choice and opacity are remembered
            in localStorage, and the preview below updates live on this page.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border border-line p-4">
            <div className="space-y-0.5">
              <Label htmlFor="scenery-toggle">Enable scenery</Label>
              <p className="text-sm text-muted-foreground">
                Shows the custom background on the Hub home page and behind this settings page.
              </p>
            </div>
            <Button
              id="scenery-toggle"
              variant={scenery ? 'default' : 'outline'}
              size="icon"
              onClick={handleToggleScenery}
              aria-pressed={scenery}
              aria-label={scenery ? 'Disable hub scenery' : 'Enable hub scenery'}
            >
              <Image className="w-4 h-4" />
            </Button>
          </div>

          <div
            className={`space-y-3 rounded-lg border border-line p-4 transition-opacity ${
              scenery ? '' : 'opacity-50'
            }`}
          >
            <div className="flex items-center justify-between">
              <Label htmlFor="scenery-opacity">Background opacity</Label>
              <span className="text-sm tabular-nums text-steel">{opacity}%</span>
            </div>
            <input
              id="scenery-opacity"
              type="range"
              min={0}
              max={100}
              step={1}
              value={opacity}
              onChange={(e) => handleOpacityChange(parseInt(e.target.value, 10))}
              disabled={!scenery}
              className="w-full h-1.5 bg-line rounded-lg appearance-none cursor-pointer accent-ink disabled:cursor-not-allowed"
            />
          </div>
        </CardContent>
      </Card>

      {isAdmin && (
        <Card>
          <CardHeader>
            <CardTitle>Developer tools</CardTitle>
            <CardDescription>
              Utilities for demoing and testing HUF against a fresh ERPNext install. Visible to
              System Managers only.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between rounded-lg border border-line p-4">
              <div className="space-y-0.5">
                <Label>Set up ERPNext demo data for testing</Label>
                <p className="text-sm text-muted-foreground">
                  Creates a Warehouse Type, Item Group, Customer Group, Territory, Price List, and
                  Fiscal Year — the minimum master data a Procedure needs to exercise a
                  customer/invoice/payment scenario. Safe to run more than once; only missing
                  records are created.
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleErpnextDemoSetup}
                disabled={demoSetupRunning}
              >
                {demoSetupRunning ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Wrench className="h-4 w-4" />
                )}
                Set up demo data
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
