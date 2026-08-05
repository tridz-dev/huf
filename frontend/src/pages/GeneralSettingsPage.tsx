import { useEffect, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { GeneralSettingsTab } from '@/components/settings/GeneralSettingsTab';
import {
  isSceneryEnabled,
  getSceneryOpacity,
  SCENERY_IMAGE_URL,
} from '@/lib/personalization';

export { GeneralSettingsPage };
export default GeneralSettingsPage;

function GeneralSettingsPage() {
  const [scenery, setScenery] = useState(false);
  const [opacity, setOpacity] = useState(55);

  useEffect(() => {
    setScenery(isSceneryEnabled());
    setOpacity(getSceneryOpacity());
  }, []);

  return (
    <div className="relative h-full overflow-auto">
      {scenery && (
        <div
          aria-hidden="true"
          className="absolute inset-0 z-0 pointer-events-none"
          style={{
            backgroundImage: `url(${SCENERY_IMAGE_URL})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            backgroundRepeat: 'no-repeat',
            backgroundAttachment: 'fixed',
            opacity: opacity / 100,
          }}
        />
      )}
      <div className="relative z-10 p-6 max-w-4xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <SlidersHorizontal className="w-6 h-6 text-muted-foreground" />
          <div>
            <h1 className="font-display text-title text-ink">General Settings</h1>
            <p className="text-sm text-muted-foreground">
              Personalization options for the HUF interface.
            </p>
          </div>
        </div>

        <GeneralSettingsTab
          scenery={scenery}
          onSceneryChange={setScenery}
          opacity={opacity}
          onOpacityChange={setOpacity}
        />
      </div>
    </div>
  );
}
