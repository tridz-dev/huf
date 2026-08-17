import { useEffect, useState } from 'react';
import { GeneralSettingsTab } from '@/components/settings/GeneralSettingsTab';
import { PageFrame } from '@/layouts/PageFrame';
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
    <>
      {scenery && (
        <div
          aria-hidden="true"
          className="fixed inset-0 z-0 pointer-events-none"
          style={{
            backgroundImage: `url(${SCENERY_IMAGE_URL})`,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
            backgroundRepeat: 'no-repeat',
            opacity: opacity / 100,
          }}
        />
      )}
      <PageFrame title="General settings" meta="Personalization options for the HUF interface" className="relative z-10">
        <div className="max-w-4xl mx-auto">
          <GeneralSettingsTab
            scenery={scenery}
            onSceneryChange={setScenery}
            opacity={opacity}
            onOpacityChange={setOpacity}
          />
        </div>
      </PageFrame>
    </>
  );
}
