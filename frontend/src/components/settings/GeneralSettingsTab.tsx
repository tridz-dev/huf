import { useEffect, useState } from 'react';
import { Image, RotateCcw } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
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

  return (
    <div className="max-w-2xl space-y-6">
      <p className="text-sm text-muted-foreground">
        Personalize the HUF interface. These preferences are stored locally in your browser.
      </p>

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
              <button
                key={id}
                type="button"
                onClick={() => handleThemeChange(id)}
                className={cn(
                  'flex flex-col gap-2 p-3 rounded-lg border-2 text-left transition-all',
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
              </button>
            ))}
          </div>

          <Button variant="ghost" size="sm" onClick={handleResetTheme} className="-ml-2">
            <RotateCcw className="w-4 h-4 mr-1.5" />
            Reset to Winter
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Hub Scenery</CardTitle>
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
    </div>
  );
}
