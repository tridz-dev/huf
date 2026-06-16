import { type HufAppManifest } from '@/services/appApi';
import AppCollectionView from './AppCollectionView';

interface Props { manifest: HufAppManifest }

export default function AppListShell({ manifest }: Props) {
  const primaryView = manifest.views[0];
  if (!primaryView) return null;
  return (
    <div className="flex flex-col h-full p-4 gap-4">
      <h1 className="text-xl font-semibold">{manifest.label}</h1>
      <AppCollectionView manifest={manifest} tableName={primaryView.table} />
    </div>
  );
}
